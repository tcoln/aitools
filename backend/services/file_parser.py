# Author: glt
# Email: guolintan@qq.com
# Created: 2026-07-22

import io
import logging

logger = logging.getLogger(__name__)

try:
    from openpyxl import load_workbook
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False
    logger.warning("openpyxl 未安装，Excel 文件解析不可用")

try:
    from docx import Document
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False
    logger.warning("python-docx 未安装，Word 文件解析不可用")

XLSX_EXTENSIONS = {".xlsx", ".xlsm", ".xltx", ".xltm"}
DOCX_EXTENSIONS = {".docx", ".docm", ".dotx", ".dotm", ".wpsx"}
LEGACY_EXTENSIONS = {
    ".xls": "旧版 Excel 格式(.xls)不支持，请另存为 .xlsx 格式",
    ".doc": "旧版 Word 格式(.doc)不支持，请另存为 .docx 格式",
    ".ppt": "旧版 PPT 格式(.ppt)不支持，请另存为 .pptx 格式",
    ".wps": "WPS 旧版格式(.wps)不支持，请另存为 .docx 或 .wpsx 格式",
}
TEXT_EXTENSIONS = {
    ".txt", ".md", ".py", ".js", ".ts", ".jsx", ".tsx", ".json", ".csv",
    ".xml", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".log", ".html",
    ".css", ".sql", ".sh", ".bash", ".env", ".gitignore", ".java", ".c",
    ".cpp", ".h", ".rs", ".go", ".rb", ".php", ".swift", ".kt", ".scala",
    ".r", ".lua", ".vim", ".conf",
}


# 根据文件扩展名解析文件内容，支持xlsx、docx、文本等格式
def parse_file(filename: str, content: bytes) -> str:
    ext = filename.lower()
    for e in (".xlsx", ".xlsm", ".xltx", ".xltm"):
        if ext.endswith(e):
            return _parse_xlsx(content)
    for e in (".docx", ".docm", ".dotx", ".dotm", ".wpsx"):
        if ext.endswith(e):
            return _parse_docx(content)
    for e, msg in LEGACY_EXTENSIONS.items():
        if ext.endswith(e):
            return f"[{msg}]"
    for e in TEXT_EXTENSIONS:
        if ext.endswith(e):
            return _parse_text(content)
    return f"[不支持解析此文件格式: {filename}]"


# 解析Excel(.xlsx)文件内容
def _parse_xlsx(content: bytes) -> str:
    if not HAS_OPENPYXL:
        return "[Excel 解析失败: openpyxl 未安装，请运行 pip install openpyxl]"
    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        parts = []
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            rows = []
            for row in ws.iter_rows(values_only=True):
                cells = [str(c) if c is not None else "" for c in row]
                rows.append(" | ".join(cells))
            if rows:
                parts.append(f"--- Sheet: {sheet_name} ---\n" + "\n".join(rows))
        wb.close()
        return "\n\n".join(parts) if parts else "[空表格]"
    except Exception as e:
        logger.error(f"Failed to parse xlsx: {e}")
        return f"[Excel 解析失败: {e}]"


# 解析Word(.docx)文件内容
def _parse_docx(content: bytes) -> str:
    if not HAS_DOCX:
        return "[Word 解析失败: python-docx 未安装，请运行 pip install python-docx]"
    try:
        doc = Document(io.BytesIO(content))
        paragraphs = []
        for para in doc.paragraphs:
            if para.text.strip():
                paragraphs.append(para.text)
        tables_text = []
        for table in doc.tables:
            for row in table.rows:
                cells = [cell.text for cell in row.cells]
                tables_text.append(" | ".join(cells))
        result = "\n".join(paragraphs)
        if tables_text:
            result += "\n\n--- 表格内容 ---\n" + "\n".join(tables_text)
        return result if result.strip() else "[空文档]"
    except Exception as e:
        logger.error(f"Failed to parse docx: {e}")
        return f"[Word 文档解析失败: {e}]"


# 解析文本文件内容，支持UTF-8和GBK编码
def _parse_text(content: bytes) -> str:
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return content.decode("gbk")
        except Exception:
            return "[无法解码文件内容]"