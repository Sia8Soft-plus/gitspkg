import paramiko
import os


def sftp_upload(host, port, username, password, local, remote):
    sf = paramiko.Transport((host, port))
    sf.connect(username=username, password=password)
    sftp = paramiko.SFTPClient.from_transport(sf)
    if os.path.isdir(local):  # 判断本地参数是目录还是文件
        for f in os.listdir(local):  # 遍历本地目录
            sftp.put(os.path.join(local + f), os.path.join(remote + f))  # 上传目录中的文件
    else:
        sftp.put(local, remote)  # 上传文件
    sf.close()
 
 
def sftp_download(host, port, username, password, local, remote):
    sf = paramiko.Transport((host, port))
    sf.connect(username=username, password=password)
    sftp = paramiko.SFTPClient.from_transport(sf)
    if os.path.isdir(local):  # 判断本地参数是目录还是文件
        for f in sftp.listdir(remote):  # 遍历远程目录
            sftp.get(os.path.join(remote + f), os.path.join(local + f))  # 下载目录中文件
    else:
        sftp.get(remote, local)  # 下载文件
    sf.close()
