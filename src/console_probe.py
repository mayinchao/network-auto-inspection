import socket
import time


HOST = "127.0.0.1"
PORT = 2000


def read_all(sock, seconds=2):
    sock.settimeout(0.2)

    end_time = time.time() + seconds
    data = b""

    while time.time() < end_time:

        try:
            chunk = sock.recv(4096)

            if not chunk:
                break

            data += chunk

        except socket.timeout:
            continue

    return data


def show(title, data):

    print()
    print("=" * 70)
    print(title)
    print("=" * 70)

    print("原始 bytes：")
    print(repr(data))

    print()

    print("UTF-8 解码：")
    print(
        data.decode(
            "utf-8",
            errors="replace",
        )
    )


def main():

    print(
        f"连接 {HOST}:{PORT} ..."
    )

    with socket.create_connection(
        (HOST, PORT),
        timeout=5,
    ) as sock:

        print("TCP连接成功")

        # 1. 什么都不发，先看端口主动返回什么
        data1 = read_all(
            sock,
            seconds=1,
        )

        show(
            "连接后主动返回",
            data1,
        )

        # 2. 发送一次回车
        print()
        print("发送：CRLF")

        sock.sendall(
            b"\r\n"
        )

        data2 = read_all(
            sock,
            seconds=2,
        )

        show(
            "发送回车后的返回",
            data2,
        )

        # 3. 发送 display version
        print()
        print(
            "发送：display version"
        )

        sock.sendall(
            b"display version\r\n"
        )

        data3 = read_all(
            sock,
            seconds=5,
        )

        show(
            "display version 原始返回",
            data3,
        )


if __name__ == "__main__":
    main()