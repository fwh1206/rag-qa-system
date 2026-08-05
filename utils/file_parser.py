"""文件解析工具：把 PDF/Word/文本/Markdown/Excel 提取为纯文本，并提供中文感知切分。"""  # 模块文档：说明本文件负责文件解析与文本切分

from langchain_text_splitters import RecursiveCharacterTextSplitter  # 导入 LangChain 递归字符切分器
from PyPDF2 import PdfReader  # 导入 PDF 读取器
from docx import Document  # 导入 Word 文档读取类


def split_text(text: str, chunk_size: int = 400, chunk_overlap: int = 50):  # 定义中文感知文本切分函数
    """基于 LangChain RecursiveCharacterTextSplitter 的中文感知分片。"""  # 函数说明文档
    if not text or not text.strip():  # 文本为空或全是空白
        return []  # 返回空列表
    if chunk_size <= 0:  # 切片大小非法
        chunk_size = 400  # 回退到默认值 400
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:  # 重叠参数非法
        chunk_overlap = max(0, chunk_size // 8)  # 重置为切片大小的八分之一
    splitter = RecursiveCharacterTextSplitter(  # 创建切分器实例
        chunk_size=chunk_size,  # 设置切片大小
        chunk_overlap=chunk_overlap,  # 设置切片重叠
        separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],  # 按优先级排列的中文分隔符
        keep_separator=True,  # 切分时保留分隔符
        length_function=len,  # 使用字符数作为长度计算函数
    )
    return [chunk.strip() for chunk in splitter.split_text(text) if chunk and chunk.strip()]  # 切分并去除空白后返回


def _read_txt(file_path: str) -> str:  # 定义读取文本文件的函数
    # 优先按 UTF-8 读取，失败时回退 GB18030
    with open(file_path, "rb") as f:  # 以二进制模式打开文件
        raw = f.read()  # 读取原始字节
    for encoding in ("utf-8-sig", "gb18030"):  # 依次尝试两种常见中文编码
        try:  # 尝试解码
            return raw.decode(encoding)  # 解码成功直接返回文本
        except UnicodeDecodeError:  # 解码失败
            continue  # 尝试下一种编码
    return raw.decode("utf-8", errors="replace")  # 全部失败时用替换模式兜底


def _read_docx(file_path: str) -> str:  # 定义读取 Word 文档的函数
    # 提取 docx 段落和表格文本，表格按行用竖线拼接
    doc = Document(file_path)  # 打开 Word 文档
    parts = [para.text for para in doc.paragraphs if para.text.strip()]  # 收集所有非空段落文本
    for table in doc.tables:  # 遍历文档中的表格
        for row in table.rows:  # 遍历表格的每一行
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]  # 收集该行非空单元格
            if cells:  # 行内有内容
                parts.append(" | ".join(cells))  # 用竖线拼接单元格并加入列表
    return "\n".join(parts)  # 用换行连接所有文本


def _read_excel(file_path: str, suffix: str) -> str:  # 定义读取 Excel 文件的函数
    # xlsx 用 openpyxl，xls 用 xlrd，输出为“工作表 + 行文本”
    if suffix == ".xlsx":  # 处理新版 Excel 格式
        from openpyxl import load_workbook  # 按需导入 openpyxl
        wb = load_workbook(file_path, read_only=True, data_only=True)  # 只读模式打开工作簿，取计算后的值
        lines = []  # 初始化输出行列表
        try:  # 确保读取后关闭工作簿
            for sheet in wb.worksheets:  # 遍历所有工作表
                lines.append(f"# 工作表：{sheet.title}")  # 添加工作表标题行
                for row in sheet.iter_rows(values_only=True):  # 遍历每一行数据
                    cells = [str(cell).strip() for cell in row if cell is not None and str(cell).strip()]  # 收集非空单元格
                    if cells:  # 行内有内容
                        lines.append(" | ".join(cells))  # 用竖线拼接并加入列表
        finally:  # 无论是否异常
            wb.close()  # 关闭工作簿
        return "\n".join(lines)  # 返回拼接后的文本

    import xlrd  # 按需导入 xlrd 处理旧版 xls
    book = xlrd.open_workbook(file_path)  # 打开 xls 工作簿
    lines = []  # 初始化输出行列表
    for sheet in book.sheets():  # 遍历所有工作表
        lines.append(f"# 工作表：{sheet.name}")  # 添加工作表标题行
        for r in range(sheet.nrows):  # 遍历每一行
            cells = []  # 初始化该行单元格列表
            for c in range(sheet.ncols):  # 遍历每一列
                value = sheet.cell_value(r, c)  # 读取单元格值
                if value not in ("", None):  # 单元格非空
                    cells.append(str(value))  # 转成字符串加入列表
            if cells:  # 行内有内容
                lines.append(" | ".join(cells))  # 用竖线拼接并加入列表
    return "\n".join(lines)  # 返回拼接后的文本


def read_file(file_path: str, suffix: str) -> str:  # 定义统一文件读取入口
    # 按后缀分发到不同解析器，统一返回纯文本
    suffix = (suffix or "").lower()  # 把后缀转成小写，兼容大写扩展名
    if suffix == ".pdf":  # PDF 文件
        reader = PdfReader(file_path)  # 创建 PDF 读取器
        pages = []  # 初始化页面文本列表
        for page in reader.pages:  # 遍历每一页
            text = page.extract_text()  # 提取页面文本
            if text:  # 页面有文本
                pages.append(text)  # 加入列表
        full_text = "\n".join(pages)  # 用换行连接所有页面
    elif suffix in (".txt", ".md"):  # 纯文本或 Markdown
        full_text = _read_txt(file_path)  # 调用文本读取函数
    elif suffix == ".docx":  # Word 文档
        full_text = _read_docx(file_path)  # 调用 Word 读取函数
    elif suffix in (".xlsx", ".xls"):  # Excel 文件
        full_text = _read_excel(file_path, suffix)  # 调用 Excel 读取函数
    else:  # 其他类型
        raise ValueError(f"不支持的文件类型：{suffix}")  # 抛出类型不支持错误
    return full_text.strip()  # 去除首尾空白后返回
