import os
import re
import json
import shutil
import hashlib

project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
prompt_dir = os.path.abspath(os.path.join(project_dir, "llm_interface"))
output_dir = os.path.join(project_dir, "fuzzing_handler", "file_output")
argvs_dir = os.path.join(project_dir, "fuzzing_handler", "argvs")
seed_dir = os.path.join(project_dir, "fuzzing_handler", "input")

exec_path_dict = {
    "avconv": "/root/programs_rq5/libav-git-c464278/build_orig/bin/", 
    "bison": "/root/programs_rq5/bison-3.7.6/build_orig/bin/", 
    "c++filt": "/root/programs_configfuzz/binutils-2.37/build_orig/bin/", 
    "cflow": "/root/programs_rq5/cflow-1.6/build_orig/bin/", 
    "cjpeg": "/root/programs_rq5/libjpeg-turbo-2.1.0/build_orig/bin/", 
    "cmark": "/root/programs/cmark-git-9c8e8/build_orig/bin/", 
    "djpeg": "/root/programs_rq5/libjpeg-turbo-2.1.0/build_orig/bin/", 
    "dwarfdump": "/root/programs_rq5/libdwarf-20210528/build_orig/bin/", 
    "editcap": "/root/programs/wireshark-4.0.1/build_orig/bin/", 
    "eu-elfclassify": "/root/programs/elfutils-0.188/build_orig/bin/", 
    "exiv2": "/root/programs_rq5/exiv2-0.27.4/build_orig/bin/", 
    "ffmpeg": "/root/programs_rq5/ffmpeg-N-103440-g2f0113be3f/build_orig/bin/", 
    "gif2png": "/root/programs_configfuzz/gif2png-2.5.8/build_orig/bin/", 
    "gm": "/root/programs_rq5/GraphicsMagick-1.3.36/build_orig/bin/", 
    "gs": "/root/programs_rq5/ghostpdl-9.54.0/build_orig/bin/", 
    "img2sixel": "/root/programs/libsixel-git-6a5be/build_orig/bin/", 
    "jasper": "/root/programs_rq5/jasper-2.0.32/build_orig/bin/", 
    "jpegoptim": "/root/programs/jpegoptim-1.5.0/build_orig/bin/", 
    "jpegtran": "/root/programs/libjpeg-turbo-2.1.4/build_orig/bin/", 
    "jq": "/root/programs/jq-1.6/build_orig/bin/", 
    "lrzip": "/root/programs/lrzip-0.651/build_orig/bin/", 
    "mpg123": "/root/programs_rq5/mpg123-1.28.2/build_orig/bin/", 
    "mutool": "/root/programs_rq5/mupdf-git-d00de0e/build_orig/bin/", 
    "nasm": "/root/programs_rq5/nasm-2.15.05/build_orig/bin/", 
    "nm": "/root/programs_configfuzz/binutils-2.37/build_orig/bin/", 
    "objdump": "/root/programs_rq5/binutils-2.36.1/build_orig/bin/", 
    "ogg123": "/root/programs/vorbis-tools-1.4.2/build_orig/bin/", 
    "openssl-asn1parse": "/root/programs/openssl-git-31ff3/build_orig/bin/", 
    "openssl-ec": "/root/programs/openssl-git-31ff3/build_orig/bin/", 
    "openssl-rsa": "/root/programs/openssl-git-31ff3/build_orig/bin/", 
    "pdftohtml": "/root/programs_rq5/poppler-21.07.0/build_orig/bin/", 
    "pdftopng": "/root/programs_rq5/xpdf-4.03/build_orig/bin/", 
    "pdftops": "/root/programs/xpdf-4.03/build_orig/bin/", 
    "pdftotext": "/root/programs/xpdf-4.03/build_orig/bin/", 
    "pngfix": "/root/programs_rq5/libpng-1.6.37/build_orig/bin/", 
    "podofoencrypt": "/root/programs/podofo-0.9.8/build_orig/bin/", 
    "pspp": "/root/programs_rq5/pspp-1.4.1/build_orig/bin/", 
    "readelf": "/root/programs_rq5/binutils-2.36.1/build_orig/bin/", 
    "size": "/root/programs_rq5/binutils-2.36.1/build_orig/bin/", 
    "speexdec": "/root/programs/speex-Speex-1.2.1/build_orig/bin/", 
    "tcpprep": "/root/programs/tcpreplay-4.4.2/build_orig/bin/", 
    "tcpreplay": "/root/programs/tcpreplay-4.4.2/build_orig/bin/", 
    "tiff2pdf": "/root/programs_rq5/tiff-4.3.0/build_orig/bin/", 
    "tiff2ps": "/root/programs_rq5/tiff-4.3.0/build_orig/bin/", 
    "tiffcp": "/root/programs/libtiff-git-b51bb/build_orig/bin/", 
    "tiffcrop": "/root/programs/libtiff-git-b51bb/build_orig/bin/", 
    "tiffinfo": "/root/programs_rq5/tiff-4.3.0/build_orig/bin/", 
    "vim": "/root/programs_rq5/vim-8.2.3113/build_orig/bin/", 
    "xmlcatalog": "/root/programs_rq5/libxml2-2.9.12/build_orig/bin/", 
    "xmllint": "/root/programs_rq5/libxml2-2.9.12/build_orig/bin/", 
    "xmlwf": "/root/programs_rq5/expat-2.4.1/build_orig/bin/", 
    "yara": "/root/programs_rq5/yara-4.1.1/build_orig/bin/"
}

def processQuotation(s):
    stack = []
    pairs = []
    escaped = set()

    tmp_list = []
    for word in s.split(" "):
        if word.startswith('\\"') or word.startswith("\\'"):
            word = '"' + word[2:]
        if word.endswith('\\"') or word.endswith("\\'"):
            word = word[:-2] + '"'
        tmp_list.append(word)
    s = ' '.join(tmp_list)
    
    i = 0
    while i < len(s):
        if s[i] == '\\' and i + 1 < len(s):
            if s[i + 1] in "\"'":
                escaped.add(i + 1)
            i += 2 
        elif s[i] in "\"'" and i not in escaped:
            if stack and stack[-1][0] == s[i]: 
                start_pos = stack.pop()[1]
                pairs.append((start_pos, i))
            else:
                stack.append((s[i], i))
            i += 1
        else:
            i += 1
    
    result = list(s)
    for start, end in pairs:
        result[start] = '"'
        result[end] = '"'
        for j in range(start + 1, end):
            if result[j] in ['"', "'"] and (j - 1 < 0 or result[j - 1] != '\\'):
                result[j] = "'"
    return ''.join(result)

def processRedirection(s):
    tmp_list = []
    for word in re.findall(r'"[^"]*"|\S+', s):
        # Remove <|> since fuzzer cannot handle them
        if word in ["<", ">"]:
            continue
        # Invalid string
        elif ("<" in word or ">" in word):
            if word[0] not in ['"', "'"] and word[:2] not in  ["\\\"", "\\'"]:
                word = f'"{word}'
            if word[-1] not in ['"', "'"] and word[-2:] not in  ["\\\"", "\\'"]:
                word = f'{word}"'
        tmp_list.append(word)

    return " ".join(tmp_list)

if __name__ == "__main__":
    with open(os.path.join(prompt_dir, "output", "file.json"), "r") as f:
        data = json.loads(f.read())

    count = 0
    print_flag = False
    for name in data.keys():
        input_file_list = []
        cmd_list = []

        for cmd_data in data[name]:
            # TODO: file in file_output without id
            id = cmd_data["id"]

            cmd = cmd_data["cmd"]
            cmd = processRedirection(cmd)
            cmd = processQuotation(cmd)
            # Escape \n
            cmd = re.sub(r'(?<!\\)\n', r'\\n', cmd)

            # Other program's cmd
            if not name.startswith(cmd.split(" ")[0]):
                continue

            placeholder_set = set()
            for placeholder in cmd_data["placeholders"]:
                basename = os.path.basename(placeholder)
                # Remove output
                if "output" in basename or "result" in basename or ("out" in basename and ".out" not in basename):
                    continue
                # Is a dir
                if basename == "":
                    placeholder_set.add(placeholder)
                else:
                    placeholder_set.add(basename)
            file_set = set([os.path.basename(n) if os.path.basename(n) != "" else n for n in cmd_data["files"]])

            # Try to fix placeholder names
            if not placeholder_set.issubset(file_set):
                new_placeholder_set = set()
                for placeholder in placeholder_set:
                    if placeholder not in file_set:
                        prefix = placeholder.split(".")[0]
                        suffix = placeholder.split(".")[-1]
                        # if "extension" in suffix:
                        replace_flag = False
                        for f in file_set:
                            if f.startswith(prefix):
                                new_placeholder_set.add(f)
                                # Update the new palceholder in cmd
                                cmd = cmd.replace(placeholder, f)
                                replace_flag = True
                                break
                        # Cannot fix such situation
                        if not replace_flag:
                            new_placeholder_set = set()
                            break
                    else:
                        new_placeholder_set.add(placeholder)

                if len(new_placeholder_set) == 0:
                    count += 1
                    continue

                placeholder_set = new_placeholder_set

            # 1. input
            # 2. only one placeholder
            # 3. source / test
            input_file = ""
            file0_flag = False
            input_flag = False
            for placeholder in placeholder_set:
                if "file0" in placeholder:
                    input_file = placeholder
                    file0_flag = True
                elif not file0_flag and "input" in placeholder:
                    input_file = placeholder
                    input_flag = True
                elif not file0_flag and not input_flag and ("test" in placeholder or "source" in placeholder):
                    input_file = placeholder
            if not input_flag and not file0_flag and input_file == "" and len(placeholder_set) == 1:
                input_file = placeholder
            
            if input_file == "":
                count += 1
                continue

            input_file_path = os.path.join(output_dir, f"{name}_{id}", [f for f in cmd_data["files"] if os.path.basename(f) == input_file][0])
            input_file_list.append(input_file_path)
            
            # We assume that files in placeholders are those that are needed to be generated
            split_list = []
            missed_placeholder_list = []
            replace_dict = {}
            for placeholder in placeholder_set:
                # Is a dir
                if os.path.basename(placeholder) == "":
                    if placeholder.endswith("/"):
                        placeholder = placeholder[:-1]

                    matches = list(re.finditer(r"(?<=\W)" + re.escape(placeholder) + r"/?(?=[^\w/\-\.])", cmd))

                    if len(matches) == 0:
                        missed_placeholder_list.append(placeholder)
                        break

                    for match in matches:
                        if placeholder.startswith("/tmp/"):
                            replace_path = os.path.join(output_dir, f"{name}_{id}", os.path.relpath(placeholder, "/tmp/"), "")
                        else:
                            replace_path = os.path.join(output_dir, f"{name}_{id}", placeholder, "")
                        split_list.append({"start": match.start(), "end": match.end(), "replace": replace_path})
                        # Create the target dir if not created
                        if os.path.exists(replace_path) == False:
                            os.makedirs(replace_path)
                # Is a file 
                else:
                    matches = list(re.finditer(r"\b" + re.escape(placeholder) + r"\b", cmd))

                    # Cannot find the placeholder in cmd
                    if len(matches) == 0:
                        # Maybe like -Pfile
                        matches = list(re.finditer(r"\s+-[a-zA-Z]+" + re.escape(placeholder) + r"\b", cmd))
                        if len(matches) == 0:
                            prefix = placeholder.split(".")[0]
                            suffix = placeholder.split(".")[-1]
                            # [0] and [-1] are not the same
                            if prefix != suffix:
                                # Try to search suffix
                                word_list = []
                                for word in cmd.split(" "):
                                    if word.endswith("'") or word.endswith('"'):
                                        word = word[1:-1]
                                    if word.endswith("." + suffix) and \
                                    "output" not in word and "result" not in word and \
                                    os.path.basename(word) not in placeholder_set:
                                        word_list.append(word)
                                # multiple matched items, we cannot operate
                                if len(set(word_list)) > 1:
                                    missed_placeholder_list.append(placeholder)
                                    break
                                elif len(set(word_list)) == 0:
                                    missed_placeholder_list.append(placeholder)
                                    break
                                # Replace the word
                                else:
                                    print_flag = True
                                    replace_dict[os.path.basename(word_list[0])] = placeholder
                                    matches = list(re.finditer(r"\b" + re.escape(os.path.basename(word_list[0])) + r"\b", cmd))

                    tmp_list = []
                    for match in matches:
                        start = match.start()
                        end = match.end()
                        # Same name of an option
                        if cmd[start - 2: start] == " -":
                            continue
                
                        if cmd[start:end] in replace_dict:
                            target_file = replace_dict[cmd[start:end]]
                        else:
                            target_file = cmd[start:end]

                        if cmd[start - 1] == "/":
                            prefix = cmd[:start].split(" ")[-1]
                            # Is an url
                            if "http:" in prefix:
                                continue
                            first_slash_pos = prefix.index("/")
                            if first_slash_pos > 0 and prefix[first_slash_pos - 1] == ".":
                                path = os.path.relpath(prefix[first_slash_pos - 1: ] + target_file, ".")
                            else:
                                path = prefix[first_slash_pos: ] + target_file
                        else:
                            prefix = ""
                            first_slash_pos = 0
                            path = os.path.relpath(target_file, ".")
    
                        tmp_list.append({"start": start - len(prefix) + first_slash_pos, "end": end, "replace": path})

                    unique_path_set = set([item["replace"] for item in tmp_list])
                    # Invalid path like an url
                    if len(unique_path_set) == 0:
                        continue
                    for item in tmp_list:
                        path = item["replace"]
                        if path.startswith("/tmp/"):
                            # Usually, path started with /tmp/ is the output path
                            if len(unique_path_set) > 1:
                                continue
                            else:
                                replace_path = os.path.join(output_dir, f"{name}_{id}", os.path.relpath(path, "/tmp/"))
                        else:
                            replace_path = os.path.join(output_dir, f"{name}_{id}", os.path.relpath(path, "."))

                        if cmd[start:end] == input_file:
                            replace_path = "@@"

                        split_list.append({"start": item["start"], "end": item["end"], "replace": replace_path})
                            
            # Some or all placeholders cannot be found in cmd
            # TODO: We try to fix these wrong placeholders
            if len(missed_placeholder_list) > 0:
                count += 1
                continue
            
            split_string_list = []
            prev = 0
            for item in sorted(split_list, key=lambda a: a["start"]):
                split_string_list.append(cmd[prev: item["start"]])
                split_string_list.append(item["replace"])
                prev = item["end"]
            split_string_list.append(cmd[prev: ])

            new_cmd = "".join(split_string_list)
            cmd_list.append(new_cmd)

        os.makedirs(os.path.join(seed_dir, name), exist_ok=True)

        id = 0
        md5_list = []
        for input_path in input_file_list:

            with open(input_path, 'rb') as f:
                md5_obj = hashlib.md5()
                md5_obj.update(f.read())
                md5 = md5_obj.hexdigest()
            
            if md5 in md5_list:
                continue

            md5_list.append(md5)

            if len(input_path.split(".")) > 1:
                suffix = input_path.split(".")[-1]
                new_name = f"{name}_{id}.{suffix}"
            else:
                new_name = f"{name}_{id}"

            shutil.copy(input_path, os.path.join(seed_dir, name, new_name))
            
            id += 1

        with open(os.path.join(argvs_dir, f"argvs_{name}.txt"), "w") as f:
            f.write(str(len(cmd_list)) + "\n" + "\n".join(cmd_list))
    