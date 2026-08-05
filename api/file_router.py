"""文件与知识库接口：负责上传解析、文本录入、向量入库、列表、删除与重建索引。"""  # 模块文档：说明本文件提供文件与知识库接口

import os  # 导入操作系统模块，用于文件路径和删除
import re  # 导入正则模块，用于校验文件名
import uuid  # 导入 UUID 模块，用于生成临时文件名

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile  # 导入路由与文件上传相关类
from pydantic import BaseModel, Field  # 导入请求体模型基类与字段校验工具

from config.settings import UPLOAD_PATH  # 导入上传目录
from core.auth import require_admin  # 导入管理员权限依赖
from core.logger import write_log  # 导入日志写入函数
from core.rag_engine import (  # 导入向量引擎相关函数
    SUPPORTED_SUFFIXES,  # 支持的文件后缀
    clear_all_vector,  # 清空向量库
    delete_file_vectors,  # 删除文件向量
    file_to_vector,  # 文件入库
    get_all_files,  # 获取文件列表
    hybrid_search,  # 混合检索
)
from utils.file_meta import (  # 导入文件元数据相关函数
    DEFAULT_CATEGORY,  # 默认分组
    clear_file_meta,  # 清空元数据
    get_file_category,  # 获取分组
    remove_file_meta,  # 删除元数据
    set_file_category,  # 设置分组
)
from utils.file_parser import read_file  # 导入文件解析函数


router = APIRouter(prefix="", tags=["文件与知识库"])  # 创建无前缀的路由，归类为“文件与知识库”

MAX_FILE_SIZE = 20 * 1024 * 1024  # 单文件最大 20MB
STREAM_CHUNK_SIZE = 1024 * 1024  # 分块读取大小 1MB
MAX_TEXT_LENGTH = 1024 * 1024  # 手动录入文本最大 1MB
INVALID_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|\r\n]')  # 文件名中的非法字符正则


class TextUpload(BaseModel):  # 定义文本录入请求体
    # 手动粘贴文本的请求体
    doc_name: str = Field(..., min_length=1, max_length=200)  # 文档名称，必填且长度 1-200
    text_content: str = Field(..., min_length=1, max_length=MAX_TEXT_LENGTH)  # 文本内容，必填且限长
    category: str = Field(DEFAULT_CATEGORY, min_length=1, max_length=50)  # 分组，默认分组


def _safe_filename(name: str) -> str:  # 定义文件名清洗函数
    # 清洗文件名，阻止路径穿越和非法字符
    safe = os.path.basename((name or "").strip())  # 只保留路径中的文件名部分，阻止路径穿越
    if not safe or safe in {".", ".."} or INVALID_FILENAME_CHARS.search(safe):  # 文件名为空、特殊值或含非法字符
        raise HTTPException(status_code=400, detail="文件名不合法")  # 返回 400 错误
    return safe  # 返回安全文件名


@router.post("/upload")  # 注册 POST /upload 接口
async def upload_file(file: UploadFile = File(...), category: str = Form(DEFAULT_CATEGORY)):  # 定义文件上传函数
    # 上传文件：先保存临时文件，再解析文本、切分并写入向量库
    filename = _safe_filename(file.filename)  # 清洗上传文件名
    category = (category or DEFAULT_CATEGORY).strip() or DEFAULT_CATEGORY  # 清洗分组名，缺省用默认分组
    write_log(f"开始上传：{filename}")  # 记录上传开始日志
    suffix = os.path.splitext(filename)[1].lower()  # 提取小写文件后缀
    if suffix not in SUPPORTED_SUFFIXES:  # 文件类型不支持
        raise HTTPException(status_code=400, detail="仅支持pdf/txt/docx/md/xlsx/xls")  # 返回 400 错误

    tmp_path = os.path.join(UPLOAD_PATH, f".{uuid.uuid4().hex}.part")  # 生成临时文件路径
    size = 0  # 初始化已接收字节数
    try:  # 捕获上传异常
        # 分块接收文件，限制单文件大小
        with open(tmp_path, "wb") as f:  # 以二进制写模式打开临时文件
            while True:  # 循环读取文件块
                chunk = await file.read(STREAM_CHUNK_SIZE)  # 异步读取一块数据
                if not chunk:  # 已读完
                    break  # 结束循环
                size += len(chunk)  # 累加字节数
                if size > MAX_FILE_SIZE:  # 超过大小限制
                    raise HTTPException(status_code=413, detail="文件过大，最大支持20MB")  # 返回 413 错误
                f.write(chunk)  # 写入临时文件

        try:  # 尝试解析文件
            text = read_file(tmp_path, suffix)  # 按后缀解析文件文本
        except Exception as exc:  # 解析失败
            write_log(f"文件解析失败：{filename}，{exc}")  # 记录解析失败日志
            raise HTTPException(status_code=400, detail="文件解析失败，请检查文件是否损坏") from exc  # 返回 400 错误
        if not text:  # 文件没有有效文本
            raise HTTPException(status_code=400, detail="文件无有效文本")  # 返回 400 错误

        chunk_num = file_to_vector(filename, text, category)  # 切分文本并写入向量库
        set_file_category(filename, category)  # 保存文件分组元数据
        # 解析成功后再把临时文件移动到正式目录
        os.replace(tmp_path, os.path.join(UPLOAD_PATH, filename))  # 用正式文件名替换临时文件
    except Exception:  # 任意异常
        if os.path.exists(tmp_path):  # 临时文件存在
            os.remove(tmp_path)  # 删除临时文件
        raise  # 继续抛出原异常
    write_log(f"文档入库成功：{filename}，切片数量：{chunk_num}")  # 记录入库成功日志
    return {"code": 200, "msg": "文档入库成功", "filename": filename, "chunk_num": chunk_num}  # 返回入库结果


@router.get("/kb/list")  # 注册 GET /kb/list 接口
def kb_list(  # 定义文件列表查询函数
    page: int = Query(1, ge=1),  # 页码，最小为 1
    page_size: int = Query(20, ge=1, le=100),  # 每页条数，范围 1-100
    category: str | None = Query(None),  # 分组过滤，可选
):
    # 分页返回知识库文件列表及每个文件的切片数
    files = get_all_files(category=category)  # 获取文件列表，可按分组过滤
    total = len(files)  # 计算文件总数
    start = (page - 1) * page_size  # 计算本页起始下标
    return {  # 返回分页结果
        "file_list": files[start:start + page_size],  # 本页文件列表
        "total": total,  # 文件总数
        "page": page,  # 当前页码
        "page_size": page_size,  # 每页条数
        "category": category,  # 当前分组过滤
    }


@router.get("/kb/categories")  # 注册 GET /kb/categories 接口
def kb_categories():  # 定义分组汇总函数
    # 汇总所有文档的分类及数量，供前端分组筛选
    counts = {}  # 保存分组名到数量的映射
    for item in get_all_files():  # 遍历全部文件
        name = item.get("category") or DEFAULT_CATEGORY  # 取分组名，缺失时用默认分组
        counts[name] = counts.get(name, 0) + 1  # 累加数量
    return {  # 返回分组列表
        "categories": [  # 分组数组
            {"name": name, "count": count}  # 每个分组包含名称和数量
            for name, count in sorted(counts.items(), key=lambda x: x[0])  # 按名称排序
        ]
    }


@router.get("/kb/preview")  # 注册 GET /kb/preview 接口
def kb_preview(filename: str = Query(..., min_length=1, max_length=255)):  # 定义文件预览函数
    # 返回文档提取后的纯文本，供前端预览和溯源跳转
    safe_name = _safe_filename(filename)  # 清洗文件名
    path = os.path.join(UPLOAD_PATH, safe_name)  # 拼接完整路径
    suffix = os.path.splitext(safe_name)[1].lower()  # 提取小写后缀
    if not os.path.isfile(path) or suffix not in SUPPORTED_SUFFIXES:  # 文件不存在或类型不支持
        raise HTTPException(status_code=404, detail="文件不存在")  # 返回 404 错误
    text = read_file(path, suffix)  # 解析文件文本
    info = next((f for f in get_all_files() if f["name"] == safe_name), {})  # 在文件列表中查找该文件信息
    return {  # 返回预览数据
        "filename": safe_name,  # 文件名
        "category": get_file_category(safe_name),  # 分组
        "size": os.path.getsize(path),  # 文件大小
        "chunk_num": info.get("chunk_num", 0),  # 切片数量
        "text": text,  # 文件文本
    }


@router.get("/kb/test")  # 注册 GET /kb/test 接口
def kb_test(  # 定义检索测试函数
    question: str = Query(..., min_length=1, max_length=2000),  # 测试问题，必填且限长
    top_k: int = Query(3, ge=1, le=10),  # 召回数量，范围 1-10
    category: str | None = Query(None),  # 分组过滤，可选
):
    # 检索测试器：只召回不问答，方便查看命中片段、相似度和 BM25 得分
    try:  # 捕获检索异常
        hits = hybrid_search(question, top_k, category)  # 执行混合检索
        results = []  # 保存测试结果
        for hit in hits:  # 遍历命中结果
            results.append({  # 组装单条结果
                "text": hit["document"],  # 命中文本
                "filename": hit.get("filename") or "未知来源",  # 来源文件名
                "chunk_index": hit.get("chunk_index") or -1,  # 片段序号
                "category": hit.get("category") or DEFAULT_CATEGORY,  # 分组
                "similarity": hit.get("similarity"),  # 相似度
                "bm25_score": hit.get("bm25_score"),  # BM25 得分
            })
        return {"results": results}  # 返回检索结果
    except Exception as exc:  # 检索异常
        write_log(f"检索测试失败：{exc}")  # 记录失败日志
        raise HTTPException(status_code=500, detail=f"检索失败：{exc}") from exc  # 返回 500 错误


@router.delete("/kb/delete", dependencies=[Depends(require_admin)])  # 注册 DELETE /kb/delete 接口，仅管理员可调用
def kb_delete(filename: str = Query(..., min_length=1, max_length=255)):  # 定义删除文件函数
    # 删除单个文件：先删向量，再删磁盘文件
    safe_name = _safe_filename(filename)  # 清洗文件名
    path = os.path.join(UPLOAD_PATH, safe_name)  # 拼接完整路径
    has_file = os.path.isfile(path)  # 判断磁盘文件是否存在
    ok = delete_file_vectors(safe_name)  # 删除该文件的所有向量
    if not ok and not has_file:  # 向量和磁盘文件都不存在
        raise HTTPException(status_code=404, detail="文件不存在")  # 返回 404 错误
    if has_file:  # 磁盘文件存在
        os.remove(path)  # 删除磁盘文件
    remove_file_meta(safe_name)  # 删除元数据记录
    return {"msg": f"{safe_name} 删除完成"}  # 返回删除完成提示


@router.delete("/kb/clear_all", dependencies=[Depends(require_admin)])  # 注册 DELETE /kb/clear_all 接口，仅管理员可调用
def kb_clear():  # 定义清空知识库函数
    # 清空向量库和磁盘上的全部文档
    clear_all_vector()  # 清空向量库
    clear_file_meta()  # 清空文件元数据
    for name in os.listdir(UPLOAD_PATH):  # 遍历上传目录
        path = os.path.join(UPLOAD_PATH, name)  # 拼接完整路径
        if os.path.isfile(path) and os.path.splitext(name)[1].lower() in SUPPORTED_SUFFIXES:  # 是支持的文件
            os.remove(path)  # 删除文件
    return {"msg": "全部知识库已清空"}  # 返回清空完成提示


@router.post("/kb/reindex", dependencies=[Depends(require_admin)])  # 注册 POST /kb/reindex 接口，仅管理员可调用
def kb_reindex():  # 定义重建索引函数
    """按当前切片配置重建全部文档向量，使切片大小/重叠修改立即生效。"""  # 函数说明文档
    # 读取 data 目录下所有支持的文件，逐个重新解析并入库
    if not os.path.isdir(UPLOAD_PATH):  # 上传目录不存在
        return {"msg": "知识库为空", "files": 0, "chunks": 0, "failed": []}  # 返回空结果
    files = sorted(  # 排序文件列表
        name  # 文件名
        for name in os.listdir(UPLOAD_PATH)  # 遍历上传目录
        if os.path.isfile(os.path.join(UPLOAD_PATH, name))  # 只保留文件
        and os.path.splitext(name)[1].lower() in SUPPORTED_SUFFIXES  # 且后缀受支持
    )
    if not files:  # 没有可重建的文件
        return {"msg": "知识库为空", "files": 0, "chunks": 0, "failed": []}  # 返回空结果

    total_chunks = 0  # 累计切片数量
    ok = 0  # 成功文件数
    failed = []  # 失败文件列表
    for name in files:  # 遍历每个文件
        path = os.path.join(UPLOAD_PATH, name)  # 拼接完整路径
        suffix = os.path.splitext(name)[1].lower()  # 提取小写后缀
        try:  # 捕获单文件异常
            text = read_file(path, suffix)  # 解析文件文本
            if not text.strip():  # 文件为空
                failed.append(name)  # 记入失败列表
                write_log(f"重建索引跳过空文档：{name}")  # 记录跳过日志
                continue  # 处理下一个文件
            total_chunks += file_to_vector(name, text, get_file_category(name))  # 重新入库并累加切片数
            ok += 1  # 成功数加一
        except Exception as exc:  # 解析或入库异常
            failed.append(name)  # 记入失败列表
            write_log(f"重建索引失败 {name}：{exc}")  # 记录失败日志
    write_log(f"重建索引完成：成功 {ok} 个文件，共 {total_chunks} 段")  # 记录完成日志
    return {  # 返回重建结果
        "msg": f"重建完成，成功 {ok} 个文件，共 {total_chunks} 段",  # 结果提示
        "files": ok,  # 成功文件数
        "chunks": total_chunks,  # 总切片数
        "failed": failed,  # 失败文件列表
    }


@router.post("/upload_text")  # 注册 POST /upload_text 接口
async def upload_text(payload: TextUpload):  # 定义文本录入函数
    # 手动粘贴文本入库：自动补 .txt/.md 后缀后走同样的切分入库流程
    doc_name = _safe_filename(payload.doc_name)  # 清洗文档名称
    category = (payload.category or DEFAULT_CATEGORY).strip() or DEFAULT_CATEGORY  # 清洗分组名
    base, ext = os.path.splitext(doc_name)  # 拆分文件名和后缀
    if ext.lower() not in (".txt", ".md"):  # 后缀不是文本格式
        doc_name = doc_name + ".txt"  # 自动补 .txt 后缀
    content = payload.text_content.strip()  # 去除文本内容首尾空白
    if not content:  # 文本为空
        raise HTTPException(status_code=400, detail="文本内容不能为空")  # 返回 400 错误

    tmp_path = os.path.join(UPLOAD_PATH, f".{uuid.uuid4().hex}.part")  # 生成临时文件路径
    try:  # 捕获录入异常
        with open(tmp_path, "w", encoding="utf-8") as f:  # 以 UTF-8 写入临时文件
            f.write(content)  # 写入文本内容
        chunk_num = file_to_vector(doc_name, content, category)  # 切分并写入向量库
        set_file_category(doc_name, category)  # 保存分组元数据
        os.replace(tmp_path, os.path.join(UPLOAD_PATH, doc_name))  # 临时文件改名为正式文件
    except Exception:  # 任意异常
        if os.path.exists(tmp_path):  # 临时文件存在
            os.remove(tmp_path)  # 删除临时文件
        raise  # 继续抛出原异常
    write_log(f"文本文档入库，名称：{doc_name}，切片数量：{chunk_num}")  # 记录入库日志
    return {"code": 200, "msg": "文本录入成功", "filename": doc_name, "chunk_num": chunk_num}  # 返回录入结果
