import json
import os
import re
from dotenv import load_dotenv
from typing import Dict, Any

load_dotenv()

try:
    from gigachat import GigaChat
    from gigachat.models import Chat, Messages, MessagesRole
    GIGACHAT_AVAILABLE = True
except ImportError:
    GIGACHAT_AVAILABLE = False
    print("Библиотека gigachat не установлена")

class GigaChatClient:
    
    def __init__(self, credentials: str = None):
        if not GIGACHAT_AVAILABLE:
            raise ImportError("gigachat не установлен")
        
        self.credentials = credentials or os.getenv("GIGACHAT_CREDENTIALS")
        
        if not self.credentials:
            raise ValueError("GIGACHAT_CREDENTIALS не найдены")
        
        self.client = GigaChat(
            credentials=self.credentials,
            verify_ssl_certs=False,
            timeout=120.0
        )
    
    def generate_typescript(self, filename: str, file_preview: dict, json_structure: Dict) -> str:
        file_ext = filename.split('.')[-1].lower()
        full_content = file_preview.get('full_content', '')
        columns = file_preview.get('columns', [])
        
        if file_ext in ['xls', 'xlsx']:
            parse_code = self._get_excel_parser(columns)
            structure_desc = self._get_excel_desc(filename, full_content, columns, file_preview)
        elif file_ext == 'csv':
            parse_code = self._get_csv_parser()
            structure_desc = self._get_csv_desc(filename, full_content, columns, file_preview)
        elif file_ext == 'pdf':
            parse_code = self._get_pdf_parser()
            structure_desc = self._get_pdf_desc(filename, full_content)
        elif file_ext == 'docx':
            parse_code = self._get_docx_parser()
            structure_desc = self._get_docx_desc(filename, full_content)
        elif file_ext in ['png', 'jpg', 'jpeg']:
            parse_code = self._get_image_parser()
            structure_desc = self._get_image_desc(filename, full_content)
        else:
            parse_code = self._get_text_parser()
            structure_desc = self._get_text_desc(filename, full_content, file_ext)
        
        prompt = f"""Сгенерируй TypeScript код для парсинга {file_ext} файла.

{structure_desc}

ВАЖНЫЕ ТРЕБОВАНИЯ:
1. Имена полей в интерфейсе DealData должны быть на АНГЛИЙСКОМ в camelCase
   Например: organizationName, innKio, isTaxResidentOnlyInRussia, controllerFullName
2. НЕ ИСПОЛЬЗУЙ русские названия полей
3. export default async function parseFile(base64file: string): Promise<DealData[]>
4. export type {{ DealData }} в конце
5. Для браузера, НЕ используй Buffer, используй atob и Uint8Array
6. Добавь try-catch, при ошибке возвращай []
7. Функции extractField и extractBoolean должны быть определены внутри parseFile
8. Заполняй поля через extractField и extractBoolean, НЕ ставь заглушки
9. Возвращай массив: return [result];

Сгенерируй ТОЛЬКО код, без пояснений."""
        
        messages = [
            Messages(role=MessagesRole.SYSTEM, content="Ты эксперт TypeScript. Анализируй содержимое файла. Создавай интерфейс DealData. Имена полей ТОЛЬКО на английском в camelCase. Для PDF используй ТОЛЬКО pdf-parse. НЕ используй fs, stream, crypto, pdf-parser. Генерируй простой код: цикл по строкам, split(':')."),
            Messages(role=MessagesRole.USER, content=prompt)
        ]
        
        response = self.client.chat(Chat(messages=messages, temperature=0.2))
        ts_code = response.choices[0].message.content
        
        ts_code = self._extract_code(ts_code)
        
        return ts_code
    
    def _get_excel_parser(self, columns):
        code = """const binaryString = atob(base64file);
    const bytes = new Uint8Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) {
      bytes[i] = binaryString.charCodeAt(i);
    }
    const workbook = XLSX.read(bytes, { type: 'array' });
    const sheet = workbook.Sheets[workbook.SheetNames[0]];
    const data = XLSX.utils.sheet_to_json(sheet);
    return data.map(row => ({"""
        
        for col in columns:
            field_name = self._col_to_field(col)
            if 'Шайбы' in col or 'гол' in col.lower():
                code += f"""
      {field_name}: Number(String(row['{col}']).split('-')[0]),"""
                code += f"""
      goalsAgainst: Number(String(row['{col}']).split('-')[1]),"""
            else:
                code += f"""
      {field_name}: row['{col}'] !== undefined ? row['{col}'] : '',"""
        
        code += """
    }));"""
        return code
    
    def _get_csv_parser(self):
        return """const text = atob(base64file);
    const lines = text.split('\\n').filter(l => l.trim());
    const headers = lines[0].split(',').map(h => h.trim());
    const result: DealData[] = [];
    for (let i = 1; i < lines.length; i++) {
      const values = lines[i].split(',').map(v => v.trim());
      const obj: any = {};
      headers.forEach((h, idx) => { obj[h] = values[idx] || ''; });
      result.push(obj as DealData);
    }
    return result;"""
    
    def _get_pdf_parser(self):
        return """import pdfParse from 'pdf-parse';

export default async function parseFile(base64file: string): Promise<DealData[]> {
  try {
    const binaryString = atob(base64file);
    const bytes = new Uint8Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) {
      bytes[i] = binaryString.charCodeAt(i);
    }
    const data = await pdfParse(bytes);
    const text = data.text;
    const lines = text.split('\\n').map(l => l.trim()).filter(l => l);
    
    const extractField = (label: string): string => {
      for (const line of lines) {
        if (line.includes(label)) {
          const colonIndex = line.indexOf(':');
          if (colonIndex !== -1) {
            return line.substring(colonIndex + 1).trim();
          }
          const match = line.match(new RegExp(`${label.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&')}[\\s:]+(.+)`, 'i'));
          if (match) return match[1].trim();
        }
      }
      return '';
    };
    
    const extractBoolean = (label: string): boolean => {
      for (const line of lines) {
        if (line.includes(label)) {
          const lowerLine = line.toLowerCase();
          if (lowerLine.includes('да') || lowerLine.includes('x') || 
              lowerLine.includes('✓') || lowerLine.includes('yes')) {
            return true;
          }
        }
      }
      return false;
    };
    
    const result: DealData = {
      // Заполни поля через extractField и extractBoolean
      // Используй camelCase
    };
    return [result];
  } catch (error) {
    console.error('Ошибка парсинга:', error);
    return [];
  }
}

export type { DealData };"""
    
    def _get_docx_parser(self):
        return """import mammoth from 'mammoth';

export default async function parseFile(base64file: string): Promise<DealData[]> {
  try {
    const binaryString = atob(base64file);
    const bytes = new Uint8Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) {
      bytes[i] = binaryString.charCodeAt(i);
    }
    const result = await mammoth.extractRawText({ buffer: bytes.buffer });
    const text = result.value;
    const lines = text.split('\\n').map(l => l.trim()).filter(l => l);
    
    const resultData: DealData = {
      organizationName: '',
      innKio: '',
      isTaxResidentOnlyInRussia: false,
      controllerFullName: '',
      disregardedEntity: false,
      foreignFinancialInstitution: false,
      usTaxpayerOwnership: false,
      signatureDate: '',
      signatoryFullName: ''
    };
    
    for (const line of lines) {
      if (line.includes('Наименование организации')) {
        resultData.organizationName = line.split(':')[1]?.trim() || '';
      }
      if (line.includes('ИНН/КИО')) {
        resultData.innKio = line.split(':')[1]?.trim() || '';
      }
      if (line.includes('Является ли выгодоприобретатель налоговым резидентом только в')) {
        const lowerLine = line.toLowerCase();
        resultData.isTaxResidentOnlyInRussia = lowerLine.includes('да') || lowerLine.includes('x');
      }
      if (line.includes('ФИО контролирующего лица')) {
        resultData.controllerFullName = line.split(':')[1]?.trim() || '';
      }
      if (line.includes('Являюсь лицом, неотделимым от собственника')) {
        resultData.disregardedEntity = line.includes('X') || line.includes('x');
      }
      if (line.includes('Иностранным финансовым институтом')) {
        resultData.foreignFinancialInstitution = line.includes('X') || line.includes('x');
      }
      if (line.includes('Более 10% акций')) {
        resultData.usTaxpayerOwnership = line.includes('X') || line.includes('x');
      }
      if (line.includes('Дата:')) {
        resultData.signatureDate = line.split(':')[1]?.trim() || '';
      }
      if (line.includes('ФИО ИП/Руководителя')) {
        resultData.signatoryFullName = line.split(':')[1]?.trim() || '';
      }
    }
    
    return [resultData];
  } catch (error) {
    console.error('Ошибка парсинга:', error);
    return [];
  }
}

export type { DealData };"""
    
    def _get_image_parser(self):
        return """const { createWorker } = require('tesseract.js');

export default async function parseFile(base64file: string): Promise<DealData[]> {
  try {
    const binaryString = atob(base64file);
    const bytes = new Uint8Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) {
      bytes[i] = binaryString.charCodeAt(i);
    }
    const worker = await createWorker('rus');
    const { data: { text } } = await worker.recognize(bytes);
    await worker.terminate();
    const lines = text.split('\\n').map(l => l.trim()).filter(l => l);
    
    const extractField = (label: string): string => {
      for (const line of lines) {
        if (line.includes(label)) {
          const colonIndex = line.indexOf(':');
          if (colonIndex !== -1) {
            return line.substring(colonIndex + 1).trim();
          }
        }
      }
      return '';
    };
    
    const result: DealData = {
      // Заполни поля через extractField
      // Используй camelCase
    };
    return [result];
  } catch (error) {
    console.error('Ошибка парсинга:', error);
    return [];
  }
}

export type { DealData };"""
    
    def _get_text_parser(self):
        return """export default async function parseFile(base64file: string): Promise<DealData[]> {
  try {
    const text = atob(base64file);
    const lines = text.split('\\n').filter(l => l.trim());
    
    const extractField = (label: string): string => {
      for (const line of lines) {
        if (line.toLowerCase().includes(label.toLowerCase())) {
          const parts = line.split(/[\\s:]+/);
          return parts.slice(1).join(' ').trim();
        }
      }
      return '';
    };
    
    const result: DealData = {
      // Заполни поля через extractField
      // Используй camelCase
    };
    return [result];
  } catch (error) {
    console.error('Ошибка парсинга:', error);
    return [];
  }
}

export type { DealData };"""
    
    def _get_excel_desc(self, filename, full_content, columns, preview):
        sample = preview.get('sample', [])
        return f"""Файл: {filename}
Тип: Excel

Вот полное содержимое файла (первые 15000 символов):
{full_content}

Колонки в файле: {columns}
Пример данных (первая строка): {json.dumps(sample[0], ensure_ascii=False) if sample else 'нет данных'}

Создай интерфейс DealData, включив в него ВСЕ колонки из файла.
Имена полей ТОЛЬКО на английском в camelCase."""
    
    def _get_csv_desc(self, filename, full_content, columns, preview):
        sample = preview.get('sample', [])
        return f"""Файл: {filename}
Тип: CSV

Вот полное содержимое файла (первые 15000 символов):
{full_content}

Колонки в файле: {columns}
Пример данных (первая строка): {json.dumps(sample[0], ensure_ascii=False) if sample else 'нет данных'}

Создай интерфейс DealData, включив в него ВСЕ колонки из файла.
Имена полей ТОЛЬКО на английском в camelCase."""
    
    def _get_pdf_desc(self, filename, full_content):
        example_code = """const result: DealData = {{
  organizationName: '',
  innKio: '',
}};
for (const line of lines) {{
  if (line.includes('Наименование организации')) {{
    result.organizationName = line.split(':')[1]?.trim() || '';
  }}
  if (line.includes('ИНН/КИО')) {{
    result.innKio = line.split(':')[1]?.trim() || '';
  }}
}}
return [result];"""
    
        return f"""Файл: {filename}
Тип: PDF

Вот полный извлеченный текст из PDF (первые 15000 символов):
{full_content}

Проанализируй текст. Найди все поля в формате "Название поля: значение".

Создай интерфейс DealData со всеми найденными полями.
Имена полей ТОЛЬКО на английском в camelCase.

ВАЖНО: Используй ТОЛЬКО библиотеку pdf-parse. НЕ используй:
- fs, stream, crypto, pdf-parser
- createReadStream, pipeline, Transform
- createPDFParser

ПРОСТАЯ РЕАЛИЗАЦИЯ:
1. import pdfParse from 'pdf-parse';
2. const data = await pdfParse(bytes);
3. const text = data.text;
4. const lines = text.split('\\n');
5. Простой цикл по строкам с if (line.includes('Название поля')) {{ поле = line.split(':')[1]?.trim() }}

Пример:
{example_code}"""
    
    def _get_docx_desc(self, filename, full_content):
        return f"""Файл: {filename}
Тип: DOCX

Вот полный извлеченный текст из DOCX (первые 15000 символов):
{full_content}

Проанализируй текст. Найди все поля в формате "Название поля: значение".

Создай интерфейс DealData со всеми найденными полями.
Имена полей ТОЛЬКО на английском в camelCase.

ВАЖНО:
1. Используй ТОЛЬКО библиотеку mammoth
2. НЕ используй pdfParse
3. Код должен быть простым: цикл по строкам, split(':')

Пример:
import mammoth from 'mammoth';

export default async function parseFile(base64file: string): Promise<DealData[]> {{
  try {{
    const binaryString = atob(base64file);
    const bytes = new Uint8Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) {{
      bytes[i] = binaryString.charCodeAt(i);
    }}
    const result = await mammoth.extractRawText({{ buffer: bytes.buffer }});
    const text = result.value;
    const lines = text.split('\\n');
    
    const resultData: DealData = {{
      organizationName: '',
      innKio: '',
    }};
    
    for (const line of lines) {{
      if (line.includes('Наименование организации')) {{
        resultData.organizationName = line.split(':')[1]?.trim() || '';
      }}
      if (line.includes('ИНН/КИО')) {{
        resultData.innKio = line.split(':')[1]?.trim() || '';
      }}
    }}
    
    return [resultData];
  }} catch (error) {{
    console.error('Ошибка парсинга:', error);
    return [];
  }}
}}

export type {{ DealData }};"""

    def _get_image_desc(self, filename, full_content):
        return f"""Файл: {filename}
Тип: Изображение

Вот текст, распознанный OCR (первые 15000 символов):
{full_content}

Проанализируй текст. Найди все поля в формате "Название поля: значение".
Создай интерфейс DealData со всеми найденными полями.
Имена полей ТОЛЬКО на английском в camelCase."""
    
    def _get_text_desc(self, filename, full_content, file_ext):
        return f"""Файл: {filename}
Тип: {file_ext}

Содержимое файла (первые 15000 символов):
{full_content}

Проанализируй содержимое. Найди все структурированные данные.
Создай интерфейс DealData со всеми найденными полями.
Имена полей ТОЛЬКО на английском в camelCase."""
    
    def _col_to_field(self, col: str) -> str:
        import re
        col_lower = col.lower()
        
        if 'команда' in col_lower:
            return 'teamName'
        if 'и' == col_lower or 'games' in col_lower:
            return 'games'
        if 'в' == col_lower or 'wins' in col_lower:
            return 'wins'
        if 'во' in col_lower:
            return 'overtimeWins'
        if 'шайбы' in col_lower or 'goals' in col_lower:
            return 'goalsFor'
        if 'о' == col_lower or 'points' in col_lower:
            return 'points'
        if 'наименование' in col_lower or 'organization' in col_lower:
            return 'organizationName'
        if 'инн' in col_lower:
            return 'innKio'
        
        cleaned = re.sub(r'[^\w\s]', '', col)
        cleaned = re.sub(r'%', 'percent', cleaned)
        words = cleaned.split()
        if not words:
            return col.lower()
        result = words[0].lower()
        for word in words[1:]:
            result += word.capitalize()
        return result
    
    def _extract_code(self, text: str) -> str:
        if '```typescript' in text:
            match = re.search(r'```typescript\n(.*?)\n```', text, re.DOTALL)
            if match:
                return match.group(1).strip()
        
        if '```' in text:
            match = re.search(r'```\n(.*?)\n```', text, re.DOTALL)
            if match:
                return match.group(1).strip()
        
        lines = text.split('\n')
        code_lines = []
        in_code = False
        
        for line in lines:
            if 'export interface' in line or 'export default' in line:
                in_code = True
            if in_code:
                code_lines.append(line)
        
        if code_lines:
            return '\n'.join(code_lines).strip()
        
        return text.strip()
    
    def count_tokens(self, text: str) -> int:
        try:
            response = self.client.tokens_count(input_=text)
            return response.tokens
        except:
            return len(text) // 4