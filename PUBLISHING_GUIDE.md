# 发布指南

本插件使用 gitflow 工作流，发布流程如下：

1. 提交代码到远程仓库
2. 打 tag 并推送到远程仓库（tag 格式为 v1.0.0）
3. 触发 github action
4. 等待 action 完成
5. 发布成功