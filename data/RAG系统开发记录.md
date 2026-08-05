# RAG 系统开发记录

## 项目架构

系统使用 FastAPI 提供 REST API，Chroma 作为本地向量数据库，MySQL 持久化用户、会话与问答历史。文档上传后先解析为纯文本，再按 chunk_size 和 chunk_overlap 切分，由 bge-small-zh 生成向量并写入 Chroma。

## 混合检索

单路向量检索对语义相近的表述效果好，但对专有名词和精确关键词容易漏召回；BM25 基于词频与逆文档频率做关键词检索，两者互补。系统先用向量和 BM25 分别召回候选，再合并去重。

## RRF 融合

倒数排名融合把两个检索结果按排名而不是分数融合，公式为 1/(60+rank)。RRF 避免了两路分数量纲不一致的问题，是常用的无监督融合方法。融合后按 RRF 分数降序返回 top_k 片段。

## 两阶段生成

第一阶段让大模型生成不超过 400 字的思考过程，分析用户意图与资料覆盖情况；第二阶段把思考结果拼进 Prompt 生成最终答案。思考过程支持开关，失败时自动降级为空内容继续回答。

## 流式输出

/chat/stream 使用 SSE 逐段返回来源、思考过程和答案 token，前端实时渲染。流式接口设置 Cache-Control: no-cache 与 X-Accel-Buffering: no，避免代理缓冲导致首字延迟。

## 评测指标

检索效果用 Recall@K 和 MRR 衡量，评测集放在 data/eval_set.json。脚本 scripts/eval_retrieval.py 会同时输出纯向量、纯 BM25 与混合检索三路基线，便于对比融合收益。
