# 端到端验证

先按 README 构建前端并用一个 Uvicorn 进程启动服务，再准备一份同时含图片和表格的 PDF：

```bash
BASE_URL=http://127.0.0.1:8080 E2E_PDF=fixtures/multimodal.pdf ./tests/e2e/full_flow.sh
```

脚本验证根路径没有登录/认证跳转或 `invalid_request`、上传后状态变为 `ready`、问答返回答案与引用字段；仅当 `/healthz` 报告 `lightrag_webui: true` 时验证 `/lightrag` 图谱页面。缺少随包 WebUI 静态资源是受支持的降级状态。
