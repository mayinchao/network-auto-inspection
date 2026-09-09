import re
import socket
import time
from datetime import datetime
from pathlib import Path


# ============================================================
# 基础配置
# ============================================================

HOST = "127.0.0.1"
PORT = 2000
DEVICE_NAME = "AR1"

OUTPUT_DIR = Path("output")
BACKUP_DIR = Path("backup")


# 普通巡检命令
INSPECTION_COMMANDS = [
    "display version",
    "display ip interface brief",
    "display ip routing-table",
]

# 配置备份命令
BACKUP_COMMAND = "display current-configuration"


# ============================================================
# Huawei Console 特征
# ============================================================

MORE_PATTERN = re.compile(
    r"-+\s*More\s*-+",
    re.IGNORECASE,
)

ANSI_PATTERN = re.compile(
    r"\x1b\[[0-9;?]*[A-Za-z]"
)


# ============================================================
# 终端输出清理
# ============================================================

def process_backspaces(text):
    """
    模拟终端中的退格效果。

    Huawei Console 在分页时可能输出大量 \b，
    如果不处理，保存文件中会出现杂乱字符。
    """

    result = []

    for char in text:
        if char == "\x08":
            if result:
                result.pop()
        else:
            result.append(char)

    return "".join(result)


def normalize_terminal_output(text):
    """
    清除 ANSI 控制符、NUL 和退格影响，
    但暂时保留 ---- More ----，
    供程序判断是否需要翻页。
    """

    text = ANSI_PATTERN.sub("", text)

    text = text.replace(
        "\x00",
        "",
    )

    text = process_backspaces(
        text
    )

    return text


def clean_terminal_output(text):
    """
    生成最终可保存的干净文本。
    """

    text = normalize_terminal_output(
        text
    )

    text = MORE_PATTERN.sub(
        "",
        text,
    )

    return text


# ============================================================
# 判断 Huawei CLI 提示符
# ============================================================

def is_device_prompt(line):
    """
    只接受真正属于 AR1 的 CLI 提示符。

    合法：
        <AR1>
        [AR1]

    不合法：
        [V200R003C00]

    因此不会再把 VRP 版本行误认为命令结束。
    """

    line = line.strip()

    return line in {
        f"<{DEVICE_NAME}>",
        f"[{DEVICE_NAME}]",
    }


# ============================================================
# 清空 Console 缓冲区
# ============================================================

def drain_socket(
    sock,
    max_wait=0.5,
):
    """
    清除上一条命令遗留在 TCP Console
    缓冲区里的数据。

    避免旧的 <AR1> 被新命令误判为结束。
    """

    old_timeout = sock.gettimeout()

    sock.settimeout(0.1)

    deadline = (
        time.time() + max_wait
    )

    data = ""

    while time.time() < deadline:

        try:
            chunk = sock.recv(4096)

            if not chunk:
                break

            data += chunk.decode(
                "utf-8",
                errors="ignore",
            )

        except socket.timeout:
            break

    sock.settimeout(
        old_timeout
    )

    return data


# ============================================================
# 接收完整命令输出
# ============================================================

def receive_command_output(
    sock,
    command,
    timeout=30,
):
    """
    接收一条 Huawei CLI 命令的完整返回。

    处理流程：

    1. 等待当前命令回显。
    2. 遇到 ---- More ---- 自动发送空格。
    3. 持续读取后续内容。
    4. 最终重新出现 <AR1> 或 [AR1] 才结束。
    """

    raw_data = ""

    deadline = (
        time.time() + timeout
    )

    sock.settimeout(0.5)

    command_seen = False

    handled_more_count = 0

    while time.time() < deadline:

        try:
            chunk = sock.recv(4096)

            if not chunk:
                break

            chunk_text = chunk.decode(
                "utf-8",
                errors="ignore",
            )

            raw_data += chunk_text

            normalized = (
                normalize_terminal_output(
                    raw_data
                )
            )

            # ------------------------------------------------
            # 确认本次命令已经真正进入设备
            # ------------------------------------------------

            if command in normalized:
                command_seen = True

            # ------------------------------------------------
            # 自动处理 ---- More ----
            # ------------------------------------------------

            current_more_count = len(
                MORE_PATTERN.findall(
                    normalized
                )
            )

            while (
                handled_more_count
                < current_more_count
            ):
                print(
                    "  检测到分页，自动继续..."
                )

                # Huawei More 翻页只需要空格
                sock.sendall(
                    b" "
                )

                handled_more_count += 1

                time.sleep(
                    0.15
                )

            # ------------------------------------------------
            # 判断命令是否真正结束
            # ------------------------------------------------

            if command_seen:

                cleaned = (
                    clean_terminal_output(
                        raw_data
                    )
                )

                lines = [
                    line.strip()
                    for line
                    in cleaned.splitlines()
                    if line.strip()
                ]

                if lines:

                    last_line = (
                        lines[-1]
                    )

                    if is_device_prompt(
                        last_line
                    ):
                        return (
                            cleaned.strip()
                        )

        except socket.timeout:
            continue

    # 超时也返回已经采集到的数据，
    # 方便后续排错
    return clean_terminal_output(
        raw_data
    ).strip()


# ============================================================
# 执行命令
# ============================================================

def send_command(
    sock,
    command,
    timeout=30,
):
    """
    向 Huawei Console 发送一条命令。
    """

    # 清理上一条命令可能残留的数据
    drain_socket(
        sock,
        max_wait=0.3,
    )

    print(
        f"[执行] {command}"
    )

    sock.sendall(
        (
            f"{command}\r\n"
        ).encode(
            "utf-8"
        )
    )

    output = (
        receive_command_output(
            sock,
            command,
            timeout=timeout,
        )
    )

    return output


# ============================================================
# 保存普通巡检结果
# ============================================================

def save_inspection_result(
    results,
    timestamp,
):
    OUTPUT_DIR.mkdir(
        exist_ok=True
    )

    output_file = (
        OUTPUT_DIR
        / (
            f"{DEVICE_NAME}"
            f"_console_"
            f"{timestamp}.txt"
        )
    )

    output_file.write_text(
        "\n\n".join(
            results
        ),
        encoding="utf-8",
    )

    return output_file


# ============================================================
# 保存配置备份
# ============================================================

def save_configuration_backup(
    config_output,
    timestamp,
):
    device_backup_dir = (
        BACKUP_DIR
        / DEVICE_NAME
    )

    device_backup_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    backup_file = (
        device_backup_dir
        / (
            f"{DEVICE_NAME}_"
            f"{timestamp}.txt"
        )
    )

    backup_file.write_text(
        config_output,
        encoding="utf-8",
    )

    return backup_file


# ============================================================
# 配置完整性检查
# ============================================================

def check_configuration(
    config_output,
):
    """
    对配置备份做简单完整性检查。
    """

    problems = []

    if len(config_output) < 500:
        problems.append(
            "配置输出长度过短"
        )

    if "sysname AR1" not in config_output:
        problems.append(
            "未检测到 sysname AR1"
        )

    if "return" not in config_output:
        problems.append(
            "未检测到配置结束标志 return"
        )

    if MORE_PATTERN.search(
        config_output
    ):
        problems.append(
            "配置中仍存在分页提示"
        )

    return problems


# ============================================================
# 主程序
# ============================================================

def main():

    print(
        f"正在连接 Huawei "
        f"{DEVICE_NAME} "
        f"({HOST}:{PORT}) ..."
    )

    with socket.create_connection(
        (HOST, PORT),
        timeout=5,
    ) as sock:

        print(
            "Console TCP连接成功"
        )

        # ----------------------------------------------------
        # 清理历史 Console 数据
        # ----------------------------------------------------

        old_data = drain_socket(
            sock,
            max_wait=0.5,
        )

        if old_data.strip():
            print(
                "已清理 Console 历史残留数据"
            )

        print(
            f"目标设备提示符："
            f"<{DEVICE_NAME}> / "
            f"[{DEVICE_NAME}]"
        )

        timestamp = (
            datetime.now().strftime(
                "%Y%m%d_%H%M%S"
            )
        )

        inspection_results = []

        # ====================================================
        # 普通 Huawei 巡检
        # ====================================================

        print()
        print(
            "========================================"
        )

        print(
            "开始 Huawei 设备巡检"
        )

        print(
            "========================================"
        )

        for command in (
            INSPECTION_COMMANDS
        ):

            output = send_command(
                sock,
                command,
                timeout=30,
            )

            section = [
                "=" * 70,
                (
                    f"DEVICE: "
                    f"{DEVICE_NAME}"
                ),
                (
                    f"CONSOLE: "
                    f"{HOST}:{PORT}"
                ),
                (
                    f"COMMAND: "
                    f"{command}"
                ),
                "=" * 70,
                output,
            ]

            inspection_results.append(
                "\n".join(
                    section
                )
            )

        output_file = (
            save_inspection_result(
                inspection_results,
                timestamp,
            )
        )

        print()
        print(
            f"巡检结果已保存："
            f"{output_file}"
        )

        # ====================================================
        # Huawei 配置自动备份
        # ====================================================

        print()
        print(
            "========================================"
        )

        print(
            "开始 Huawei 配置备份"
        )

        print(
            "========================================"
        )

        config_output = (
            send_command(
                sock,
                BACKUP_COMMAND,
                timeout=120,
            )
        )

        config_length = len(
            config_output
        )

        print()
        print(
            f"配置输出长度："
            f"{config_length} 字符"
        )

        # ====================================================
        # 配置完整性检查
        # ====================================================

        problems = (
            check_configuration(
                config_output
            )
        )

        if problems:

            print()
            print(
                "配置完整性检查：WARNING"
            )

            for problem in problems:
                print(
                    f"  - {problem}"
                )

        else:

            print()
            print(
                "配置完整性检查：PASS"
            )

            print(
                "  - 已检测到 sysname AR1"
            )

            print(
                "  - 已检测到 return"
            )

            print(
                "  - 未发现残留分页提示"
            )

        # ====================================================
        # 保存配置
        # ====================================================

        backup_file = (
            save_configuration_backup(
                config_output,
                timestamp,
            )
        )

        print()
        print(
            f"配置备份已保存："
            f"{backup_file}"
        )

        print()
        print(
            "========================================"
        )

        print(
            "Huawei Console 自动巡检完成"
        )

        print(
            "========================================"
        )


if __name__ == "__main__":
    main()