import os
import requests
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from google import genai 
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup Gemini Client
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

app = FastAPI()

# Ensure the static folder exists
if not os.path.exists("static"):
    os.makedirs("static")

# Mount static files for HTML/CSS
app.mount("/static", StaticFiles(directory="static"), name="static")

class RoadmapRequest(BaseModel):
    skill: str
    language: str = "Any"
    speed: str
    custom_prompt: str = ""

@app.post("/generate")
async def generate_roadmap(req: RoadmapRequest):
    custom_context = f" {req.custom_prompt}" if req.custom_prompt else ""
    
    prompt = f"""Create a Mermaid flowchart for learning {req.skill}.
Pace: {req.speed}.{custom_context}

IMPORTANT RULES:
1. Start with: graph TD
2. Use simple node IDs: A, B, C, etc
3. Put labels in square brackets: A[Label Text]
4. Avoid special characters in labels (no colons, quotes)
5. Connect nodes: A --> B
6. All nodes must be connected to the graph
7. No explanations, just the graph code

Example:
graph TD
    A[Start] --> B[Learn Basics]
    B --> C[Practice]
    C --> D[Build Project]

Generate the roadmap now:"""
    
    try:
        print("=" * 70)
        print(f"Request: {req.skill} ({req.speed})")
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        
        # Extract text
        mermaid_code = None
        
        try:
            if hasattr(response, 'text'):
                mermaid_code = response.text
                print("Extracted via response.text")
        except Exception as e:
            print(f"Method 1 failed: {e}")
            try:
                if response.candidates and len(response.candidates) > 0:
                    candidate = response.candidates[0]
                    if candidate.content and candidate.content.parts:
                        text_parts = []
                        for part in candidate.content.parts:
                            if hasattr(part, 'text') and part.text:
                                text_parts.append(part.text)
                        if text_parts:
                            mermaid_code = ''.join(text_parts)
                            print("Extracted via candidates")
            except Exception as e2:
                print(f"Method 2 failed: {e2}")
        
        if not mermaid_code:
            return {"error": "Could not generate content"}
        
        # Clean the code
        mermaid_code = mermaid_code.strip()
        mermaid_code = mermaid_code.replace('```mermaid', '')
        mermaid_code = mermaid_code.replace('```', '')
        mermaid_code = mermaid_code.strip()
        
        # Find where graph starts
        if not mermaid_code.startswith('graph'):
            lines = mermaid_code.split('\n')
            for i in range(len(lines)):
                if lines[i].strip().startswith('graph'):
                    mermaid_code = '\n'.join(lines[i:])
                    break
        
        # Clean up the syntax - remove problematic characters from labels
        lines = mermaid_code.split('\n')
        cleaned_lines = []
        for line in lines:
            # Keep the line structure but clean it up
            cleaned_line = line
            # Replace problematic punctuation in brackets
            if '[' in line and ']' in line:
                # Simple cleanup - you can make this more sophisticated
                cleaned_line = line.replace(':', ' -')
            cleaned_lines.append(cleaned_line)
        
        mermaid_code = '\n'.join(cleaned_lines)
        
        if 'graph TD' not in mermaid_code and 'graph LR' not in mermaid_code:
            return {"error": "No valid graph found", "raw": mermaid_code[:300]}
        
        print(f"Cleaned code (first 500 chars):\n{mermaid_code[:500]}")
        print("=" * 70)
        
        # Send to Kroki
        print("Sending to Kroki...")
        kroki_response = requests.post(
            "https://kroki.io/mermaid/svg",
            json={
                "diagram_source": mermaid_code,
                "diagram_type": "mermaid", 
                "output_format": "svg"
            },
            headers={"Content-Type": "application/json"},
            timeout=20
        )
        
        print(f"Kroki status: {kroki_response.status_code}")
        
        if kroki_response.status_code == 200:
            print("Success!")
            return {
                "mermaid": mermaid_code,
                "svg": kroki_response.text,
                "success": True
            }
        else:
            error_msg = kroki_response.text
            print(f"Kroki error: {error_msg}")
            
            # Try to provide helpful error message
            if "syntax" in error_msg.lower():
                return {
                    "error": "The generated diagram has syntax errors. Try a simpler request.",
                    "mermaid": mermaid_code,
                    "details": error_msg[:300]
                }
            else:
                return {
                    "error": f"Diagram rendering failed",
                    "mermaid": mermaid_code,
                    "details": error_msg[:300]
                }
    
    except Exception as e:
        import traceback
        print(f"Exception: {str(e)}")
        print(traceback.format_exc())
        return {"error": f"Server error: {str(e)}"}

@app.get("/", response_class=HTMLResponse)
async def read_index():
    index_path = os.path.join("static", "index.html")
    if os.path.exists(index_path):
        with open(index_path, encoding='utf-8') as f:
            return f.read()
    return "Error: static/index.html not found."

