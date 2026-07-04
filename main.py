from fastapi import FastAPI, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import json
from generator import TypeScriptGenerator

app = FastAPI(title="TypeScript Code Generator API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

generator = TypeScriptGenerator()

def extract_structure(json_data: dict) -> dict:
    if isinstance(json_data, list) and len(json_data) > 0:
        return extract_structure(json_data[0])
    
    if "input" in json_data and isinstance(json_data["input"], list) and len(json_data["input"]) > 0:
        return extract_structure(json_data["input"][0])
    
    if "data" in json_data and isinstance(json_data["data"], list) and len(json_data["data"]) > 0:
        return extract_structure(json_data["data"][0])
    
    if "items" in json_data and isinstance(json_data["items"], list) and len(json_data["items"]) > 0:
        return extract_structure(json_data["items"][0])
    
    return json_data

@app.get("/")
def root():
    return {"message": "TypeScript Code Generator API с GigaChat", "status": "ok"}

@app.post("/generate")
async def generate_code(
    file: UploadFile = File(...),
    json_example: str = Form(...)
):
    try:
        content = await file.read()
        
        try:
            raw_json = json.loads(json_example)
        except json.JSONDecodeError:
            try:
                raw_json = eval(json_example)
            except:
                return JSONResponse({
                    "success": False,
                    "error": "Неверный формат json_example"
                }, status_code=400)
        
        json_structure = extract_structure(raw_json)
        
        result = await generator.generate(
            filename=file.filename,
            file_content=content,
            json_structure=json_structure
        )
        
        lines_count = len(result["ts_code"].split('\n'))
        
        return JSONResponse({
            "success": True,
            "ts_code": result["ts_code"],
            "lines_count": lines_count,
            "file_type": file.filename.split('.')[-1].lower(),
            "tokens_used": result["tokens_used"],
            "used_structure": json_structure
        })
        
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=500)

@app.get("/health")
def health_check():
    return {"status": "healthy"}