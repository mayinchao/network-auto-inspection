from datetime import datetime
from getpass import getpass
from pathlib import Path

import paramiko


HOST = "127.0.0.1"
PORT = 22
USERNAME = "netauto"

COMMANDS = [
    "hostname",
    "whoami",
    "ipconfig",
]


def decode_output(data: bytes) -> str:
    """兼容 Windows 中文命令输出。"""
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

    results = []

    try:
        print(f"正在连接 {HOST}:{PORT} ...")

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

        print("SSH 连接成功\n")

        for command in COMMANDS:
            print(f"[执行] {command}")

            stdin, stdout, stderr = client.exec_command(command)

            output = decode_output(stdout.read()).strip()
            error = decode_output(stderr.read()).strip()

            result = [
                "=" * 60,
                f"COMMAND: {command}",
                "=" * 60,
                output,
            ]

            if error:
                result.extend([
                    "",
                    "[STDERR]",
                    error,
                ])

            results.append("\n".join(result))

        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_dir / f"inspection_{timestamp}.txt"

        output_file.write_text(
            "\n\n".join(results),
            encoding="utf-8",
        )

        print(f"\n巡检完成，结果已保存：{output_file}")

    except paramiko.AuthenticationException:
        print("SSH 认证失败：请检查用户名和密码。")

    except paramiko.SSHException as e:
        print(f"SSH 协议错误：{e}")

    except TimeoutError:
        print("SSH 连接超时。")

    except Exception as e:
        print(f"程序运行失败：{e}")

    finally:
        client.close()


if __name__ == "__main__":
    main()