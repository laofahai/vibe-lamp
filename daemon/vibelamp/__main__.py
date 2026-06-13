import logging
from .server import serve


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    try:
        serve()
    except KeyboardInterrupt:
        # Ctrl-C 兜底：正常情况下 SIGINT 已由 serve() 内的信号处理器优雅收尾，
        # 此处再兜一层，确保异常路径下也干净退出、不打印堆栈。
        logging.getLogger("vibelamp").info("收到中断，守护进程已退出")


if __name__ == "__main__":
    main()
