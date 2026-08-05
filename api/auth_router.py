"""登录鉴权接口：负责登录、登出和查询当前登录用户。"""  # 模块文档：说明本文件提供登录鉴权相关接口

from fastapi import APIRouter, Depends, Header, HTTPException  # 导入路由、依赖注入、请求头与异常类
from pydantic import BaseModel, Field  # 导入请求体模型基类与字段校验工具

from config.settings import AUTH_ENABLED  # 导入鉴权开关配置
from core.auth import login, require_admin, revoke_token, validate_token  # 导入登录、权限与 token 函数
from core.database import (  # 从数据库层导入用户管理函数
    count_admins,  # 统计管理员数量
    create_user,  # 创建用户
    delete_user,  # 删除用户
    get_user,  # 查询单个用户
    list_users,  # 查询用户列表
    update_user_password,  # 修改用户密码
    update_user_role,  # 修改用户角色
)


router = APIRouter(prefix="/auth", tags=["登录鉴权"])  # 创建 /auth 前缀的路由，归类为“登录鉴权”


class LoginRequest(BaseModel):  # 定义登录请求体模型
    # 登录请求体，限制用户名和密码长度
    username: str = Field(..., min_length=1, max_length=64)  # 用户名，必填且长度 1-64
    password: str = Field(..., min_length=1, max_length=128)  # 密码，必填且长度 1-128


class RegisterRequest(BaseModel):  # 定义注册请求体模型
    # 注册请求体，密码至少 4 位，与管理员创建用户的规则一致
    username: str = Field(..., min_length=1, max_length=64)  # 用户名，必填且长度 1-64
    password: str = Field(..., min_length=4, max_length=128)  # 密码，必填且长度 4-128


class UserCreate(BaseModel):  # 定义创建用户请求体模型
    username: str = Field(..., min_length=1, max_length=64)  # 用户名，必填且长度 1-64
    password: str = Field(..., min_length=4, max_length=128)  # 密码，必填且长度 4-128
    role: str = Field("user", pattern="^(admin|user)$")  # 角色，默认 user，仅允许 admin 或 user


class UserUpdate(BaseModel):  # 定义更新用户请求体模型
    role: str | None = Field(None, pattern="^(admin|user)$")  # 新角色，可选，仅允许 admin 或 user
    password: str | None = Field(None, min_length=4, max_length=128)  # 新密码，可选且长度 4-128


@router.post("/login")  # 注册 POST /auth/login 接口
def auth_login(payload: LoginRequest):  # 定义登录处理函数
    # 校验账号密码并签发 token
    token = login(payload.username.strip(), payload.password)  # 去除用户名首尾空格后调用登录函数
    if not token:  # 登录失败
        raise HTTPException(status_code=401, detail="用户名或密码错误")  # 返回 401 错误
    user = get_user(payload.username.strip())  # 查询该用户的数据库记录
    role = user["role"] if user else "admin"  # 有记录取数据库角色，否则默认管理员
    return {  # 返回登录成功信息
        "token": token,  # 签发的 token
        "username": payload.username.strip(),  # 登录用户名
        "role": role,  # 用户角色
        "auth_enabled": AUTH_ENABLED,  # 是否启用鉴权
    }


@router.post("/logout")  # 注册 POST /auth/logout 接口
def auth_logout(x_auth_token: str | None = Header(default=None)):  # 定义登出处理函数，token 从请求头读取
    # 使当前 token 失效
    if x_auth_token:  # 请求头携带了 token
        revoke_token(x_auth_token)  # 注销该 token
    return {"msg": "已退出登录"}  # 返回登出成功提示


@router.get("/me")  # 注册 GET /auth/me 接口
def auth_me(x_auth_token: str | None = Header(default=None)):  # 定义查询当前用户函数
    # 返回当前登录状态；未启用鉴权时固定为 guest
    if AUTH_ENABLED:  # 如果启用了鉴权
        info = validate_token(x_auth_token or "")  # 校验请求携带的 token
        return {  # 返回登录用户信息
            "username": (info or {}).get("username"),  # 用户名
            "role": (info or {}).get("role"),  # 角色
            "auth_enabled": True,  # 鉴权已启用
        }
    return {"username": "guest", "role": "admin", "auth_enabled": False}  # 未启用鉴权时返回访客管理员


@router.post("/register")  # 注册 POST /auth/register 接口
def auth_register(payload: RegisterRequest):  # 定义用户自助注册函数
    # 自助注册：统一创建为普通用户；管理员由系统内置账号或管理员手动分配
    username = payload.username.strip()  # 去除用户名首尾空格
    if get_user(username):  # 用户名已存在
        raise HTTPException(status_code=400, detail="用户名已存在")  # 返回 400 错误
    if not create_user(username, payload.password, "user"):  # 以普通用户角色创建账号
        raise HTTPException(status_code=400, detail="注册失败，请稍后重试")  # 返回 400 错误
    return {"msg": "注册成功", "username": username}  # 返回注册成功信息


@router.get("/users")  # 注册 GET /auth/users 接口
def auth_users_list(_: dict = Depends(require_admin)):  # 定义查询用户列表函数，要求管理员权限
    return {"users": list_users()}  # 返回全部用户


@router.post("/users")  # 注册 POST /auth/users 接口
def auth_users_create(payload: UserCreate, _: dict = Depends(require_admin)):  # 定义创建用户函数，要求管理员权限
    if get_user(payload.username):  # 用户名已存在
        raise HTTPException(status_code=400, detail="用户名已存在")  # 返回 400 错误
    if not create_user(payload.username, payload.password, payload.role):  # 创建失败
        raise HTTPException(status_code=400, detail="用户创建失败")  # 返回 400 错误
    return {"msg": "用户创建成功", "username": payload.username}  # 返回创建成功信息


@router.put("/users/{username}")  # 注册 PUT /auth/users/{username} 接口
def auth_users_update(  # 定义更新用户函数
    username: str,  # 路径参数：要更新的用户名
    payload: UserUpdate,  # 请求体：新的角色或密码
    _: dict = Depends(require_admin),  # 要求管理员权限
):
    if not get_user(username):  # 用户不存在
        raise HTTPException(status_code=404, detail="用户不存在")  # 返回 404 错误
    if payload.role:  # 提供了新角色
        update_user_role(username, payload.role)  # 更新角色
    if payload.password:  # 提供了新密码
        update_user_password(username, payload.password)  # 更新密码
    return {"msg": "用户信息已更新", "username": username}  # 返回更新成功信息


@router.delete("/users/{username}")  # 注册 DELETE /auth/users/{username} 接口
def auth_users_delete(  # 定义删除用户函数
    username: str,  # 路径参数：要删除的用户名
    current: dict = Depends(require_admin),  # 要求管理员权限，并取得当前用户信息
):
    if username == current["username"]:  # 删除的是自己
        raise HTTPException(status_code=400, detail="不能删除当前登录账号")  # 返回 400 错误
    target = get_user(username)  # 查询目标用户
    if not target:  # 目标用户不存在
        raise HTTPException(status_code=404, detail="用户不存在")  # 返回 404 错误
    if target["role"] == "admin" and count_admins() <= 1:  # 目标是最后一个管理员
        raise HTTPException(status_code=400, detail="至少保留一个管理员")  # 返回 400 错误
    delete_user(username)  # 删除用户
    return {"msg": "用户已删除", "username": username}  # 返回删除成功信息
