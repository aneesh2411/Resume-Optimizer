from pydantic import BaseModel
from typing import Optional


class CompileJob(BaseModel):
    job_id: str
    latex_content: str
    user_id: str


class CompileResult(BaseModel):
    job_id: str
    success: bool
    pdf_url: Optional[str] = None
    error: Optional[str] = None
    compile_log: Optional[str] = None
    page_count: int = 0
