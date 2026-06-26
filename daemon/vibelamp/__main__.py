import logging
import sys
from .server import serve
from . import ota


def _run_ota(argv):
    path = None
    url = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--url" and i + 1 < len(argv):
            url = argv[i + 1]; i += 2
        elif a in ("-h", "--help"):
            print("用法: python -m vibelamp ota [firmware.bin] [--url http://设备.local/update]")
            raise SystemExit(0)
        elif path is None:
            path = a; i += 1
        else:
            print("未知参数: " + a)
            raise SystemExit(2)
    ok = ota.upload(path, url=url)
    print("OTA 上传成功，设备正在重启" if ok else "OTA 上传失败")
    raise SystemExit(0 if ok else 1)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    if len(sys.argv) > 1 and sys.argv[1] == "ota":
        _run_ota(sys.argv[2:])
    try:
        serve()
    except KeyboardInterrupt:
        # Ctrl-C 兜底：正常情况下 SIGINT 已由 serve() 内的信号处理器优雅收尾，
        # 此处再兜一层，确保异常路径下也干净退出、不打印堆栈。
        logging.getLogger("vibelamp").info("收到中断，守护进程已退出")


if __name__ == "__main__":
    main()
