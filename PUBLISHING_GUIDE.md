# 发布指南

本插件使用 gitflow 工作流，发布流程如下：

1. 提交代码到远程仓库
2. 打 tag 并推送到远程仓库（tag 格式为 v1.0.0）
3. 触发 github action
4. 等待 action 完成
5. 发布成功

## 需要配置的变量

请在 github 仓库的 settings -> secrets and variables -> actions 中配置 Repository secrets 以下变量：

- DOOTASK_USERNAME: DooTask AppStore 用户名
- DOOTASK_PASSWORD: DooTask AppStore 密码
- DOCKERHUB_USERNAME: Docker Hub 用户名
- DOCKERHUB_TOKEN: Docker Hub 密码（Token）