from getpass import getpass

import paramiko


HOST = "127.0.0.1"
PORT = 22
USERNAME = "netauto"


password = getpass("SSH password: ")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

try:
    client.connect(
        hostname=HOST,
        port=PORT,
        username=USERNAME,
        password=password,
        timeout=10,
        look_for_keys=False,
        allow_agent=False,
    )

    print("SSH 连接成功")

    stdin, stdout, stderr = client.exec_command("hostname")

    output = stdout.read().decode(errors="replace").strip()
    error = stderr.read().decode(errors="replace").strip()

    print("命令执行结果：")
    print(output)

    if error:
        print("错误信息：")
        print(error)

except paramiko.AuthenticationException:
    print("SSH 认证失败：请检查用户名或密码")

except paramiko.SSHException as e:
    print(f"SSH 错误：{e}")

except Exception as e:
    print(f"连接失败：{e}")

finally:
    client.close()