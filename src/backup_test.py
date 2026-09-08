from datetime import datetime
from getpass import getpass
from pathlib import Path

import paramiko


HOST = "127.0.0.1"
PORT = 22
USERNAME = "netauto"
DEVICE_NAME = "WIN-TEST"

# Windows阶段暂时用它模拟“设备配置”
# 后续接入华为设备后替换为：
# display current-configuration
BACKUP_COMMAND = "ipconfig /all"


def decode_output(data: bytes) -> str:
    for encoding in ("utf-8", "gbk"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue

    return data.decode("utf-8", errors="replace")


def main():
    password = getpass("SSH password: ")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        print(f"正在连接 {DEVICE_NAME} ...")

        client.connect(
            hostname=HOST,
            port=PORT,
            username=USERNAME,
            password=password,
            timeout=10,
            auth_timeout=10,
            banner_timeout=10,
            look_for_keys=False,
            allow_agent=False,
        )

        print("SSH连接成功")
        print(f"正在执行备份命令：{BACKUP_COMMAND}")

        stdin, stdout, stderr = client.exec_command(
            BACKUP_COMMAND
        )

        output = decode_output(
            stdout.read()
        ).strip()

        error = decode_output(
            stderr.read()
        ).strip()

        if error:
            print("命令返回错误：")
            print(error)

        backup_dir = Path("backup") / DEVICE_NAME
        backup_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )

        backup_file = (
            backup_dir
            / f"{DEVICE_NAME}_{timestamp}.txt"
        )

        backup_file.write_text(
            output,
            encoding="utf-8",
        )

        print("备份完成")
        print(f"备份文件：{backup_file}")

    except paramiko.AuthenticationException:
        print("SSH认证失败")

    except paramiko.SSHException as error:
        print(f"SSH协议错误：{error}")

    except Exception as error:
        print(f"备份失败：{error}")

    finally:
        client.close()


if __name__ == "__main__":
    main()