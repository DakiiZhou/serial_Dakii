# -*- coding: utf-8 -*-
# @Organization  : 
# @Author        : dkzhou
# @Time          : 
# @Function      : Serial类库封装，支持串口通信
# @Usage         :
import re
import time
import logging as log
from datetime import datetime

import serial


def rec_filter(str_content):
    """
    去除从串口读取到的返回值有很多暂不需要的编码

    :param str str_content: 字符串内容
    :return: - 字符串内容, 将带不关心的字符去除
    :rtype: str
    """
    str_content = str_content.replace('\x1b[1;34m', '')
    str_content = str_content.replace('\x1b[1;32m', '')
    str_content = str_content.replace('\x1b[0;0m', '')
    str_content = str_content.replace('\x1b[0m', '')
    str_content = str_content.replace('\x1b[33;22m', '')
    str_content = str_content.replace('\x1b[31;22m', '')
    str_content = str_content.replace('\x1b[35;22m', '')
    str_content = str_content.replace('\x1b[36;22m', '')
    str_content = str_content.encode('gbk', 'ignore')
    return str_content.decode('utf-8', 'ignore')


def check_keywords(keywords=None, content=None):
    """
    检查串口是否打印关键字
    :param keywords: 所查关键字
    :param content: 串口打印日志
    :return: True：找到关键字 False：未找到关键字
    :rtype: bool
    """
    found_tag = True
    if keywords in str(content):
        log.info("Successfully found keywords:{}".format(keywords))
    else:
        log.warning("Unsuccessfully found keywords:{}".format(keywords))
        found_tag = False
    return found_tag


def get_ip(ser):
    """
    通过正则表达式匹配ipv4地址。如果设备没有获取到ip地址，则返回-1

    :param ser: 串口实例
    :return: ip addr or -1
    :rtype: str
    """
    ip_evb = "-1"
    recv = ser.execute("ifconfig")
    inet_addr = re.findall(r"inet addr:\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9]?[0-9])\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9]?[0-9])\b", recv)
    if inet_addr:
        ip_evb = inet_addr[0].replace("inet addr:", "")
    return ip_evb


def get_network_err(ser):
    """
    获取ifconfig指令下RX/TX packets error数 错包超过20需要重置

    :param ser: 串口实例
    :return: err_tag
    :rtype: bool
    """
    err_tag = True
    recv = ser.execute("ifconfig")
    err_net = re.findall(r"errors:[0-9]+", recv)
    err_num = err_net[0].replace("errors:", "")
    if int(err_num) > 20:
        err_tag = False
    return err_tag


def check_evb_status(ser, gpio):
    """
    Check evb network status.Evb will Reboot if dhcp failed or network error.

    :param ser: 串口实例
    :param gpio: 树莓派控制IO
    :return: null
    """
    ip = get_ip(ser)
    if ip == '-1':
        log.error("<-----IP NOR FOUND ! It will REBOOT immediately!!!------>")
        #reboot(ser, gpio=gpio)
        check_evb_status(ser, gpio=gpio)

    err = get_network_err(ser)
    if not err:
        log.error("<-----Network RX ERROR exceeds the upper limit ! It will REBOOT immediately!!!------>")
        #reboot(ser, gpio=gpio)
        check_evb_status(ser, gpio=gpio)


class Serial:
    def __init__(self, com, baudrate=115200, timeout=1):
        """
        串口会话

        :param str com: USB Serial Port,
        :param int baudrate: 波特率, 常用 115200(bps)
        :param float timeout: 超时, second
        :return: Serial Session
        """
        self.port = com
        self.baud = baudrate
        self.timeout = timeout
        try:
            self.ser = serial.Serial(port=self.port, baudrate=self.baud, bytesize=8, parity='N', timeout=self.timeout)
            if self.ser.is_open:
                self.ser.reset_input_buffer()
                self.ser.reset_output_buffer()
        except Exception as e:
            if "PermissionError(13, '拒绝访问。', None, 5)" in e.args[0]:
                log.error(format(e))
                assert False, fr'当前串口 {com} 已被占用, 请检查并排除占用后重试'
            else:
                log.error(format(e))
                assert False, f'\nException: ' + format(e)

    def read_port(self, readtime=1):
        """
        从串口读取一段时间(秒)内的数据

        :param float readtime: reading seconds
        :return: read_content
        :rtype: str
        """
        start_time = datetime.now()
        _read_content = ""
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()
        while (datetime.now() - start_time).seconds < readtime:
            data_count = self.ser.in_waiting
            if data_count != 0:
                _recv = self.ser.read_until().decode("utf-8", "ignore")
                recv_sty = rec_filter(_recv)
                _read_content += recv_sty
        read_content = rec_filter(_read_content)
        return read_content

    def read_until(self, keyword, read_timeout=10):
        """
        读取串口数据,直至出现关键字, 否则超时退出

        .. note:: - 不保证返回的结果中一定有 keyword, 因为可能超时退出
                  - keyword 当前只支持纯文本, 不支持正则表达式匹配

        :param str keyword: 串口关键字
        :param float read_timeout: 读取超时
        :return: serial content
        :rtype: str
        """
        max_bytes_size = 10485760  # 10MB = 10 * 1024 * 1024 B
        ser_content = b''
        b_keyword = bytes(keyword.encode(encoding='utf-8'))  # str to bytes
        old_timeout = self.timeout
        self.ser.timeout = read_timeout
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()
        ser_content += self.ser.read_until(expected=b_keyword, size=max_bytes_size)
        _str_content = ser_content.decode("utf-8", "ignore")
        str_content = rec_filter(_str_content)
        log.info(f"tag：{str_content}")
        # print(str_content, end='', flush=True)
        self.timeout = old_timeout
        self.ser.timeout = old_timeout
        return str_content

    def send_cmd(self, cmd):
        cmd = "\n" + str(cmd) + "\n"
        final_cmd = bytes(cmd, encoding='utf-8')
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()
        self.ser.write(b'\n')  # 先回车再输入命令,排除有些cmd执行完后未回到/ #
        number_of_bytes_sent = self.ser.write(final_cmd)
        print(f'[Sent command]:{cmd}')  # for debug: 显示发送的串口命令
        return number_of_bytes_sent

    def close_port(self):
        """
        关闭端口
        """
        if self.ser is not None and self.ser.is_open:
            self.ser.close()

    @property
    def is_open(self):
        """
        端口状态
        """
        return self.ser.is_open

    def ctrl_c(self):
        """中断指令"""
        self.ser.write(chr(0x03).encode())

    def execute(self, cmd, keyword="", read_time=1, until_tag=False):
        """
        整合read与send操作，如果keyword为空 则返回content；不为空则返回Boolean
        """
        ret = ""
        ret_content = ""
        if self.is_open:
            now_time = time.time()
            self.send_cmd(cmd)
            if until_tag:
                while time.time() - now_time < read_time:
                    ret_temp = self.read_port(0.5)
                    ret_content += ret_temp
                    if keyword == "":
                        ret += ret_temp
                    else:
                        ret = keyword in ret_temp
                        if ret:
                            break
            else:
                ret_temp = self.read_port(read_time)
                if keyword == "":
                    ret = ret_temp
                else:
                    find_tag = check_keywords(keyword, ret_temp)
                    ret = find_tag
                ret_content += ret_temp
        log.info(f"[Serial Log]:" + format(ret_content))
        return ret

    def mount_nfs(self, ip, path, keyword):
        """
        挂载 没有返回值 会直接判断是否挂载成功
        :param ip: mount sever ip
        :param path: mount path
        :param keyword: make sure mount successful
        """
        mount_cmd = rf'mount -t nfs -o nolock {ip}:{path} /mnt;cd /mnt/;ls'
        recv = self.execute("ls")
        if keyword in recv:
            log.info("Already Mount!")
        else:
            mount_log = self.execute(cmd=mount_cmd)
            if keyword in mount_log:
                log.info("Mount success!:%s" % mount_log)
            elif 'Network is unreachable' in mount_log:
                log.error("Network is unreachable！Please reboot the device.received：{}".format(recv))
                self.final_serial()
                assert False, ("Network is unreachable！Please reboot the device.received：{}".format(recv))
            elif 'failed' in mount_log:
                log.warning("Failed! :%s" % mount_log)
                self.final_serial()
                assert False, "Mount failed! :%s" % mount_log

    def final_serial(self):
        if self.is_open:
            self.close_port()

# if __name__ == '__main__':
#     ser = Serial('COM3')
#     ser.send_cmd(r'test_mpp_venc -i CITY_704x576_30_orig_01.yuv -w 704 -h 576 -c 0 -g 50 -f 30 -t h265 -b 4000 -o '
#                  r'result/test_704x576_g50_f30_b4000.h265')
#     recv = ser.read_until('sendFrame 200', 10)
#     print(recv)
#     print(type(recv))
