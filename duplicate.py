import os

# 功能1：找出所有文件名中含有"(1)"、"(2)"、"(3)"的文件，并找出不包含这些的同名文件
def find_special_and_counterpart_files(directory):
    # 找出所有含有"(1)"、"(2)"、"(3)"的文件
    special_files = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            if any(f"({num})" in file for num in ['1', '2', '3', '4', '5']) and not file.endswith('.lrc'):
                cleaned_name = file.replace('(1)', '').replace('(2)', '').replace('(3)', '').rsplit('.', 1)[0].rstrip()
                special_files.append((os.path.join(root, file), cleaned_name))
                # special_files.append((os.path.join(root, file), file))

    for special_file, special_name in special_files:
        print(f"File: {special_file} , filename: {special_name}")

    # 根据含有"(1)"、"(2)"、"(3)"的文件，找出不含有这些的同名文件
    counterpart_files = {}


    for special_file, special_name in special_files:
        found_counterpart = False
        for root, dirs, files in os.walk(directory):
            for file in files:
                if any(f"({num})" in file for num in ['1', '2', '3', '4', '5']) or file.endswith('.lrc'):
                    continue  # 跳过含有"(1)"、"(2)"、"(3)"的文件
                base_name = file.rsplit('.', 1)[0]  # 获取不含扩展名的文件名
                   # base_name_without_parentheses = ''.join([s for s in base_name if not s.isdigit() and not s.startswith('(') and not s.endswith(')')])
                # print(base_name_without_parentheses)
                
           
                if special_name == base_name:
                    # print(special_name, base_name)
                    # if special_name.rsplit('.', 1)[0].startswith(base_name_without_parentheses) and special_name.rsplit('.', 1)[0].endswith(base_name.rsplit('.', 1)[0].split(base_name_without_parentheses)[1]):
                    counterpart_files[special_file] = os.path.join(root, file)
                    found_counterpart = True
                    break
        if not found_counterpart:
            counterpart_files[special_file] = "None"  # 如果没有找到对应的文件，则value为None

    return special_files, counterpart_files

# 设置目录路径
directory = 'D:\\music\\'

# 执行功能1
special_files, counterpart_files = find_special_and_counterpart_files(directory)

# 打印结果
print("Files with '(1)', '(2)', '(3)' and their counterparts:")
for file, counterpart in counterpart_files.items():
    if counterpart is not None:
        print(f"File: {file}, Counterpart: {counterpart}")
    else:
        print(f"File: {file}, No counterpart found")
