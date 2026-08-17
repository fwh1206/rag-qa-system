"""邮箱验证码发送：基于标准库 smtplib，配置 SMTP 后启用真实发送。"""

import secrets
import smtplib
from email.message import EmailMessage

from config.email_config import load_email_config
from core.logger import write_log


def generate_verification_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _send_message(email: str, subject: str, body: str) -> bool:
    cfg = load_email_config()
    if not cfg.get("host"):
        write_log(f"未配置 SMTP，跳过邮件发送：{email} ({subject})")
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg.get("from_address") or cfg.get("user") or ""
    msg["To"] = email
    msg.set_content(body)

    try:
        if cfg.get("use_ssl"):
            with smtplib.SMTP_SSL(
                cfg["host"],
                int(cfg.get("port") or 465),
                timeout=10,
                local_hostname="localhost",
            ) as server:
                if cfg.get("user"):
                    server.login(cfg["user"], cfg.get("password") or "")
                server.send_message(msg)
        else:
            with smtplib.SMTP(
                cfg["host"],
                int(cfg.get("port") or 587),
                timeout=10,
                local_hostname="localhost",
            ) as server:
                server.starttls()
                if cfg.get("user"):
                    server.login(cfg["user"], cfg.get("password") or "")
                server.send_message(msg)
        write_log(f"邮件已发送：{email} ({subject})")
        return True
    except Exception as exc:
        write_log(f"邮件发送失败：{email} ({subject})：{exc}")
        return False


def send_verification_email(email: str, code: str, purpose: str = "register") -> bool:
    """发送 6 位验证码；未配置 SMTP 时返回 False，由上层决定是否走开发模式。"""
    if purpose == "register":
        subject = "智答工作台注册验证码"
    elif purpose == "reset":
        subject = "智答工作台找回密码验证码"
    elif purpose == "bind":
        subject = "智答工作台绑定邮箱验证码"
    else:
        subject = "智答工作台登录验证码"
    body = (
        f"你的{subject}为：{code}\n"
        f"验证码 10 分钟内有效，请勿泄露给他人。\n"
        f"如果不是你本人操作，请忽略本邮件。"
    )
    return _send_message(email, subject, body)


def send_test_email(email: str) -> bool:
    """发送一封 SMTP 连通性测试邮件，供系统设置页验证邮箱配置。"""
    return _send_message(
        email,
        "智答工作台测试邮件",
        "这是一封来自智答工作台的测试邮件，说明 SMTP 邮箱配置已生效。",
    )
