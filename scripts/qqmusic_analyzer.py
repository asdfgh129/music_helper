#!/usr/bin/env python3
"""
QQ音乐流量包分析脚本
使用方法: python qqmusic_analyzer.py <pcap_file>
"""

import subprocess
import json
import re
import sys
import os
from collections import Counter, defaultdict
from datetime import datetime

# QQ音乐相关域名特征 [citation:7]
QQMUSIC_DOMAINS = [
    r'\.y\.qq\.com$',
    r'y\.qq\.com$',
    r'y\.gtimg\.cn$',
    r'music\.tc\.qq\.com$',
    r'tencentmusic\.com$',
    r'qqmusic\.qq\.com$',
    r'stat\.y\.qq\.com$',  # 数据上报域名 [citation:5]
    r'u\.y\.qq\.com$',      # API接口域名 [citation:6]
    r'c\.y\.qq\.com$',      # 搜索API [citation:10]
    r'dl\.stream\.qqmusic\.qq\.com$'  # 音乐流媒体域名 [citation:6]
]

# QQ音乐UserAgent特征 [citation:7]
QQMUSIC_UA_PATTERN = r'^QQMusic'

def check_tshark():
    """检查tshark是否可用"""
    try:
        subprocess.run(['tshark', '--version'], capture_output=True, check=True)
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        return False

def extract_dns_queries(pcap_file):
    """提取DNS查询中可能属于QQ音乐的域名"""
    print("[*] 分析DNS查询...")
    
    # tshark命令：提取DNS查询的域名
    cmd = [
        'tshark', '-r', pcap_file,
        '-Y', 'dns.qry.name',
        '-T', 'fields',
        '-e', 'dns.qry.name',
        '-e', 'frame.time_relative',
        '-E', 'separator=|'
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        qq_domains = []
        
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
                
            parts = line.split('|')
            if len(parts) >= 1:
                domain = parts[0].strip()
                # 检查是否匹配QQ音乐域名特征
                for pattern in QQMUSIC_DOMAINS:
                    if re.search(pattern, domain):
                        time = parts[1] if len(parts) > 1 else "未知"
                        qq_domains.append((domain, time))
                        break
        
        return qq_domains
    except subprocess.CalledProcessError as e:
        print(f"[-] DNS提取失败: {e}")
        return []

def extract_http_tls_connections(pcap_file):
    """提取HTTP/TLS连接中的QQ音乐通信"""
    print("[*] 分析HTTP/TLS连接...")
    
    # 提取HTTP Host和TLS SNI [citation:7]
    cmd = [
        'tshark', '-r', pcap_file,
        '-Y', 'http.host or tls.handshake.extensions_server_name',
        '-T', 'fields',
        '-e', 'frame.time_relative',
        '-e', 'ip.src',
        '-e', 'ip.dst',
        '-e', 'http.host',
        '-e', 'tls.handshake.extensions_server_name',
        '-e', 'tcp.port',
        '-e', 'frame.len',
        '-E', 'separator=|',
        '-E', 'quote=n'
    ]
    
    connections = []
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
                
            parts = line.split('|')
            if len(parts) < 5:
                continue
                
            time = parts[0]
            src_ip = parts[1]
            dst_ip = parts[2]
            http_host = parts[3] if parts[3] else None
            tls_sni = parts[4] if parts[4] else None
            port = parts[5] if len(parts) > 5 else ""
            length = parts[6] if len(parts) > 6 else "0"
            
            # 检查是否匹配QQ音乐域名
            host_to_check = http_host or tls_sni
            if host_to_check:
                for pattern in QQMUSIC_DOMAINS:
                    if re.search(pattern, host_to_check):
                        connections.append({
                            'time': time,
                            'src_ip': src_ip,
                            'dst_ip': dst_ip,
                            'host': host_to_check,
                            'port': port,
                            'length': int(length),
                            'type': 'HTTP' if http_host else 'TLS'
                        })
                        break
        
        return connections
    except subprocess.CalledProcessError as e:
        print(f"[-] 连接提取失败: {e}")
        return []

def extract_qqmusic_ip_connections(pcap_file, qq_domains, http_tls_conns):
    """
    提取所有与QQ音乐相关的IP通信
    由于QQ音乐使用HTTPDNS和长连，很多通信直接是IP [citation:3]
    """
    print("[*] 分析IP通信模式...")
    
    # 从已识别的连接中收集QQ音乐相关IP
    qq_ips = set()
    for conn in http_tls_conns:
        qq_ips.add(conn['dst_ip'])
    
    # 如果没有识别到IP，则基于域名解析关系来推断 [citation:2]
    if not qq_ips and qq_domains:
        print("[!] 未直接识别到QQ音乐IP，尝试通过DNS关联...")
        # 这里可以扩展：通过DNS响应包关联IP
    
    # 提取与这些IP的所有通信
    if not qq_ips:
        print("[!] 未识别到QQ音乐相关IP")
        return []
    
    ip_list = ' or '.join([f'ip.addr=={ip}' for ip in qq_ips])
    cmd = [
        'tshark', '-r', pcap_file,
        '-Y', ip_list,
        '-T', 'fields',
        '-e', 'frame.time_relative',
        '-e', 'ip.src',
        '-e', 'ip.dst',
        '-e', 'frame.len',
        '-e', 'frame.protocols',
        '-E', 'separator=|'
    ]
    
    all_conns = []
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
                
            parts = line.split('|')
            if len(parts) >= 4:
                all_conns.append({
                    'time': float(parts[0]),
                    'src_ip': parts[1],
                    'dst_ip': parts[2],
                    'length': int(parts[3]),
                    'protocols': parts[4] if len(parts) > 4 else 'unknown'
                })
        
        return all_conns
    except subprocess.CalledProcessError as e:
        print(f"[-] IP通信提取失败: {e}")
        return []

def analyze_traffic_patterns(connections):
    """分析通信模式"""
    if not connections:
        return {}
    
    # 统计与每个IP的通信量
    ip_traffic = defaultdict(lambda: {'packets': 0, 'bytes': 0, 'first_seen': None, 'last_seen': None})
    
    for conn in connections:
        # 关注的是与QQ音乐服务器的通信，所以看dst_ip
        # 但双向通信都要统计
        for ip in [conn['src_ip'], conn['dst_ip']]:
            ip_traffic[ip]['packets'] += 1
            ip_traffic[ip]['bytes'] += conn['length']
            
            # 记录时间范围
            if ip_traffic[ip]['first_seen'] is None or conn['time'] < ip_traffic[ip]['first_seen']:
                ip_traffic[ip]['first_seen'] = conn['time']
            if ip_traffic[ip]['last_seen'] is None or conn['time'] > ip_traffic[ip]['last_seen']:
                ip_traffic[ip]['last_seen'] = conn['time']
    
    # 识别可能的QQ音乐服务器IP（接收流量较多的IP）
    server_ips = []
    for ip, stats in ip_traffic.items():
        # 简单的启发式：如果这个IP收到的包比发出的多，可能是服务器
        # 这里简化处理，实际可能需要更复杂的逻辑
        if stats['bytes'] > 1000:  # 假设有显著流量的才是服务器
            server_ips.append((ip, stats))
    
    return dict(ip_traffic)

def generate_report(pcap_file, dns_queries, http_tls_conns, ip_connections, traffic_stats):
    """生成分析报告"""
    report = []
    report.append("=" * 60)
    report.append(f"QQ音乐流量分析报告")
    report.append(f"分析文件: {pcap_file}")
    report.append(f"分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("=" * 60)
    
    # 1. DNS查询统计
    report.append("\n[1] QQ音乐相关DNS查询")
    if dns_queries:
        domain_counter = Counter([d[0] for d in dns_queries])
        for domain, count in domain_counter.most_common():
            report.append(f"  - {domain} (出现 {count} 次)")
    else:
        report.append("  未发现QQ音乐相关DNS查询")
    
    # 2. HTTP/TLS连接
    report.append("\n[2] HTTP/TLS连接详情")
    if http_tls_conns:
        for conn in http_tls_conns[:10]:  # 只显示前10个
            report.append(f"  - [{conn['time']}s] {conn['src_ip']} -> {conn['host']} ({conn['dst_ip']}:{conn['port']}) [{conn['type']}]")
        if len(http_tls_conns) > 10:
            report.append(f"  ... 还有 {len(http_tls_conns) - 10} 条连接未显示")
    else:
        report.append("  未发现QQ音乐HTTP/TLS连接")
    
    # 3. 流量统计
    report.append("\n[3] IP通信统计")
    if traffic_stats:
        # 按流量排序
        sorted_ips = sorted(traffic_stats.items(), key=lambda x: x[1]['bytes'], reverse=True)
        report.append(f"  {'IP地址':<20} {'数据包':<10} {'流量(bytes)':<15} {'持续时间(s)':<15}")
        report.append("  " + "-" * 60)
        for ip, stats in sorted_ips[:10]:
            duration = stats['last_seen'] - stats['first_seen'] if stats['first_seen'] and stats['last_seen'] else 0
            report.append(f"  {ip:<20} {stats['packets']:<10} {stats['bytes']:<15} {duration:<15.2f}")
    else:
        report.append("  无流量统计")
    
    # 4. 总结和建议
    report.append("\n[4] 分析总结")
    if http_tls_conns:
        report.append(f"  - 发现 {len(http_tls_conns)} 条QQ音乐应用层连接")
        report.append(f"  - 涉及 {len(traffic_stats)} 个IP地址")
        
        # 检测是否使用了HTTPDNS（大量IP连接但域名较少）[citation:3]
        if len(traffic_stats) > 20 and len(dns_queries) < 5:
            report.append("  - 检测到HTTPDNS特征：直接连接多个IP，DNS查询较少")
        
        # 检测数据上报 [citation:5]
        report_conns = [c for c in http_tls_conns if 'stat.y.qq.com' in c.get('host', '')]
        if report_conns:
            report.append(f"  - 发现 {len(report_conns)} 条数据上报连接")
    
    report.append("\n" + "=" * 60)
    return "\n".join(report)

def main():
    if len(sys.argv) != 2:
        print("用法: python qqmusic_analyzer.py <pcap_file>")
        sys.exit(1)
    
    pcap_file = sys.argv[1]
    
    if not os.path.exists(pcap_file):
        print(f"[-] 文件不存在: {pcap_file}")
        sys.exit(1)
    
    if not check_tshark():
        print("[-] 未找到tshark，请安装Wireshark并确保tshark在PATH中")
        sys.exit(1)
    
    print(f"[+] 开始分析 {pcap_file}")
    
    # 执行分析
    dns_queries = extract_dns_queries(pcap_file)
    print(f"[+] 发现 {len(dns_queries)} 条QQ音乐DNS查询")
    
    http_tls_conns = extract_http_tls_connections(pcap_file)
    print(f"[+] 发现 {len(http_tls_conns)} 条QQ音乐HTTP/TLS连接")
    
    ip_connections = extract_qqmusic_ip_connections(pcap_file, dns_queries, http_tls_conns)
    print(f"[+] 发现 {len(ip_connections)} 条相关IP通信")
    
    traffic_stats = analyze_traffic_patterns(ip_connections)
    
    # 生成报告
    report = generate_report(pcap_file, dns_queries, http_tls_conns, ip_connections, traffic_stats)
    
    # 保存报告
    report_file = f"qqmusic_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"\n[+] 分析完成！报告已保存到: {report_file}")
    print(report)

if __name__ == "__main__":
    main()