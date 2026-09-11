import re
import socket
import time
from datetime import datetime
from pathlib import Path


# ============================================================
# 项目路径
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

OUTPUT_DIR = BASE_DIR / "output"
BACKUP_DIR = BASE_DIR / "backup"
DEBUG_DIR = BASE_DIR / "output" / "debug"


# ============================================================
# Huawei 设备信息
# ============================================================

HOST = "127.0.0.1"
PORT = 2000
DEVICE_NAME = "AR1"


# ============================================================
# 巡检命令
# ============================================================

INSPECTION_COMMANDS = [
    {
        "command": "display version",
        "required_any": [
            "Huawei Versatile Routing Platform",
            "VRP (R) software",
            "VRP",
        ],
        "timeout": 30,
    },
    {
        "command": "display ip interface brief",
        "required_any": [
            "IP Address/Mask",
            "Physical",
            "Protocol",
        ],
        "timeout": 30,
    },
    {
        "command": "display ip routing-table",
        "required_any": [
            "Routing Tables",
            "Destination/Mask",
            "Route Flags",
        ],
        "timeout": 30,
    },
]


BACKUP_COMMAND = {
    "command": "display current-configuration",
    "required_all": [
        f"sysname {DEVICE_NAME}",
        "return",
    ],
    "timeout": 120,
}


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
# 文本清理
# ============================================================

def normalize_terminal_output(text):
    """
    做最基础的终端清理。

    注意：
    不再使用“退格就删除前一个字符”的激进算法，
    避免把 Huawei 的真实输出误删。
    """

    text = ANSI_PATTERN.sub(
        "",
        text,
    )

    text = text.replace(
        "\x00",
        "",
    )

    text = text.replace(
        "\r",
        "",
    )

    return text


def clean_terminal_output(text):
    """
    用于最终保存的干净文本。
    """

    text = normalize_terminal_output(
        text
    )

    # 删除分页文字
    text = MORE_PATTERN.sub(
        "",
        text,
    )

    # 删除常见终端控制字符
    text = text.replace(
        "\x08",
        "",
    )

    text = text.replace(
        "\x07",
        "",
    )

    return text.strip()


# ============================================================
# Huawei CLI 提示符判断
# ============================================================

def is_device_prompt(line):
    """
    只把真正的 Huawei AR1 提示符视为提示符。

    合法：
        <AR1>
        [AR1]

    不合法：
        #
        [V200R003C00]
    """

    line = line.strip()

    return line in {
        f"<{DEVICE_NAME}>",
        f"[{DEVICE_NAME}]",
    }


def get_last_nonempty_line(text):
    """
    取得最后一个非空行。
    """

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    if not lines:
        return ""

    return lines[-1]


# ============================================================
# TCP 缓冲区处理
# ============================================================

def drain_socket(
    sock,
    max_wait=0.3,
):
    """
    清除上一次 Console 操作遗留的数据。
    """

    old_timeout = sock.gettimeout()

    sock.settimeout(
        0.1
    )

    deadline = (
        time.time()
        + max_wait
    )

    data = ""

    while time.time() < deadline:

        try:

            chunk = sock.recv(
                4096
            )

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
# Console 简单唤醒
# ============================================================

def wake_console(sock):
    """
    只负责尽量唤醒 Console。

    不再强制要求必须得到 <AR1>，
    因为 eNSP Console TCP 并不保证每次按回车
    都重新发送提示符。
    """

    print(
        "正在准备 Huawei Console..."
    )

    old_data = drain_socket(
        sock,
        max_wait=0.5,
    )

    if old_data.strip():

        print(
            "已清理 Console 历史残留数据"
        )

    # 只发送普通回车，不再发 Ctrl+C
    sock.sendall(
        b"\r\n"
    )

    time.sleep(
        0.3
    )

    response = drain_socket(
        sock,
        max_wait=0.5,
    )

    cleaned = clean_terminal_output(
        response
    )

    last_line = get_last_nonempty_line(
        cleaned
    )

    if is_device_prompt(
        last_line
    ):

        print(
            f"检测到 Huawei CLI：{last_line}"
        )

    else:

        print(
            "Console未主动回显提示符，"
            "继续通过命令输出进行验证。"
        )


# ============================================================
# 判断命令结果是否有效
# ============================================================

def validate_output(
    text,
    required_any=None,
    required_all=None,
):
    """
    判断命令返回结果是否具备预期内容。
    """

    if required_any:

        if not any(
            keyword in text
            for keyword in required_any
        ):

            return False

    if required_all:

        if not all(
            keyword in text
            for keyword in required_all
        ):

            return False

    return True


# ============================================================
# 自动分页 + 命令接收
# ============================================================

def receive_command_output(
    sock,
    command,
    required_any=None,
    required_all=None,
    timeout=30,
    quiet_period=1.2,
):
    """
    接收 Huawei 命令输出。

    完成条件有两种：

    1. 输出已经通过内容校验，并且最后出现真实提示符；
    2. 输出已经通过内容校验，并且超过 quiet_period
       没有收到新数据。

    第二种用于兼容 eNSP Console 不稳定回显提示符的情况。
    """

    raw_data = ""

    deadline = (
        time.time()
        + timeout
    )

    last_receive_time = None

    handled_more_count = 0

    sock.settimeout(
        0.3
    )

    while time.time() < deadline:

        try:

            chunk = sock.recv(
                4096
            )

            if not chunk:
                break

            last_receive_time = (
                time.time()
            )

            raw_data += chunk.decode(
                "utf-8",
                errors="ignore",
            )

            normalized = (
                normalize_terminal_output(
                    raw_data
                )
            )

            # ================================================
            # Huawei ---- More ---- 自动翻页
            # ================================================

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

                sock.sendall(
                    b" "
                )

                handled_more_count += 1

                time.sleep(
                    0.15
                )

            # ================================================
            # 内容验证
            # ================================================

            cleaned = clean_terminal_output(
                raw_data
            )

            valid = validate_output(
                cleaned,
                required_any=required_any,
                required_all=required_all,
            )

            if valid:

                last_line = (
                    get_last_nonempty_line(
                        cleaned
                    )
                )

                # 最理想情况：
                # 得到真正 Huawei CLI 提示符
                if is_device_prompt(
                    last_line
                ):

                    return cleaned

        except socket.timeout:

            # ================================================
            # eNSP 可能不给最终提示符。
            #
            # 如果已经拿到了符合预期的完整业务内容，
            # 且一段时间没有继续返回数据，
            # 也可认为该命令结束。
            # ================================================

            if last_receive_time is None:
                continue

            cleaned = clean_terminal_output(
                raw_data
            )

            valid = validate_output(
                cleaned,
                required_any=required_any,
                required_all=required_all,
            )

            silent_time = (
                time.time()
                - last_receive_time
            )

            if (
                valid
                and silent_time
                >= quiet_period
            ):

                return cleaned

            continue

    cleaned = clean_terminal_output(
        raw_data
    )

    raise TimeoutError(
        "\n"
        f"命令执行失败或输出不完整：{command}\n"
        f"已收到内容：\n"
        f"{cleaned[-1000:]}"
    )


# ============================================================
# 保存失败调试数据
# ============================================================

def save_debug_output(
    command,
    raw_text,
):
    """
    当某条命令失败时保存调试信息。
    """

    DEBUG_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = (
        datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )
    )

    safe_command = (
        command
        .replace(
            " ",
            "_",
        )
        .replace(
            "/",
            "_",
        )
    )

    debug_file = (
        DEBUG_DIR
        / (
            f"{DEVICE_NAME}_"
            f"{safe_command}_"
            f"{timestamp}.txt"
        )
    )

    debug_file.write_text(
        raw_text,
        encoding="utf-8",
    )

    return debug_file


# ============================================================
# 执行命令
# ============================================================

def send_command(
    sock,
    command,
    required_any=None,
    required_all=None,
    timeout=30,
):
    """
    清理缓冲 → 发送命令 → 接收 → 校验。
    """

    drain_socket(
        sock,
        max_wait=0.2,
    )

    print(
        f"[执行] {command}"
    )

    sock.sendall(
        (
            command
            + "\r\n"
        ).encode(
            "utf-8"
        )
    )

    try:

        output = (
            receive_command_output(
                sock,
                command,
                required_any=required_any,
                required_all=required_all,
                timeout=timeout,
            )
        )

    except Exception as exc:

        debug_file = (
            save_debug_output(
                command,
                str(exc),
            )
        )

        raise RuntimeError(
            f"{exc}\n"
            f"调试信息已保存："
            f"{debug_file}"
        ) from exc

    # ========================================================
    # 防止只收到 # 之类垃圾内容
    # ========================================================

    meaningful = output

    meaningful = meaningful.replace(
        command,
        "",
    )

    meaningful = meaningful.replace(
        f"<{DEVICE_NAME}>",
        "",
    )

    meaningful = meaningful.replace(
        f"[{DEVICE_NAME}]",
        "",
    )

    meaningful = meaningful.replace(
        "#",
        "",
    )

    meaningful = meaningful.strip()

    if len(meaningful) < 5:

        raise RuntimeError(
            f"命令 {command} "
            f"返回有效内容过短："
            f"{meaningful!r}"
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
        parents=True,
        exist_ok=True,
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

    backup_dir = (
        BACKUP_DIR
        / DEVICE_NAME
    )

    backup_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    backup_file = (
        backup_dir
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

    problems = []

    if len(config_output) < 500:

        problems.append(
            "配置输出长度过短"
        )

    if (
        f"sysname {DEVICE_NAME}"
        not in config_output
    ):

        problems.append(
            f"未检测到 sysname "
            f"{DEVICE_NAME}"
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

        # ====================================================
        # 不再强制同步提示符
        # ====================================================

        wake_console(
            sock
        )

        timestamp = (
            datetime.now().strftime(
                "%Y%m%d_%H%M%S"
            )
        )

        inspection_results = []

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

        # ====================================================
        # 巡检命令
        # ====================================================

        for item in INSPECTION_COMMANDS:

            command = item[
                "command"
            ]

            try:

                output = (
                    send_command(
                        sock,
                        command,
                        required_any=item.get(
                            "required_any"
                        ),
                        required_all=item.get(
                            "required_all"
                        ),
                        timeout=item.get(
                            "timeout",
                            30,
                        ),
                    )
                )

            except Exception as exc:

                print()
                print(
                    "巡检采集失败"
                )

                print(
                    exc
                )

                print()
                print(
                    "本次不会生成假成功巡检文件。"
                )

                return

            section = [
                "=" * 70,
                f"DEVICE: {DEVICE_NAME}",
                f"CONSOLE: {HOST}:{PORT}",
                f"COMMAND: {command}",
                "=" * 70,
                output,
            ]

            inspection_results.append(
                "\n".join(
                    section
                )
            )

        # ====================================================
        # 所有巡检命令成功以后才保存
        # ====================================================

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
        # 配置备份
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

        try:

            config_output = (
                send_command(
                    sock,
                    BACKUP_COMMAND[
                        "command"
                    ],
                    required_any=(
                        BACKUP_COMMAND.get(
                            "required_any"
                        )
                    ),
                    required_all=(
                        BACKUP_COMMAND.get(
                            "required_all"
                        )
                    ),
                    timeout=(
                        BACKUP_COMMAND.get(
                            "timeout",
                            120,
                        )
                    ),
                )
            )

        except Exception as exc:

            print()
            print(
                "配置采集失败"
            )

            print(
                exc
            )

            print()
            print(
                "本次不会保存无效配置备份。"
            )

            return

        # ====================================================
        # 配置完整性
        # ====================================================

        config_length = len(
            config_output
        )

        print()
        print(
            f"配置输出长度："
            f"{config_length} 字符"
        )

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

            print()
            print(
                "完整性检查未通过，"
                "不保存为有效配置备份。"
            )

            return

        print()
        print(
            "配置完整性检查：PASS"
        )

        print(
            f"  - 已检测到 sysname "
            f"{DEVICE_NAME}"
        )

        print(
            "  - 已检测到 return"
        )

        print(
            "  - 未发现残留分页提示"
        )

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