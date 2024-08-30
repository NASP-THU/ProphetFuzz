import re
import shutil
import subprocess


class GroffUtil:
    def __init__(self):
        self.man_version = self.__checkManVersion()
        return

    def parseGroff(self, groff_path):
        prog_name = ''
        groff_data = {"description": "", "options": {}, "synopsis": ""}
        infinding_option = 0
        current_option = ''

        with open(groff_path, 'r', encoding='utf-8') as f:
            try:
                # Remove some unnecessary tag
                content = re.sub(r'^\s*\.NOP\s+', '', f.read(), flags=re.MULTILINE).replace('\\f\\*[B-Font]', '').replace('\\f[]', '').replace('\\f\\*[I-Font]', '').replace(".BI", ".B")
                lines = content.splitlines()
            except:
                print("[ERROR] Failed to read file: %s" % groff_path)
                return -1
        
        i = 0
        already_find_name_flag, already_find_option_flag, already_find_synopsis_flag, already_find_description_flag = 0, 0, 0, 0
        parsing_type = ''
        option_section_names = []
        for i in range(len(lines)):
            if lines[i][:3] == '.TH':
                prog_name = lines[i].split(' ')[1]
                if len(prog_name) >= 2 and prog_name[0] == '"' and prog_name[-1] == '"':
                    prog_name = prog_name[1:-1]
            elif lines[i][:3] == '.SH':
                if 'name' in lines[i].lower():
                    # already done
                    if already_find_name_flag == 1:
                        parsing_type = ''
                        continue
                    parsing_type = "name"
                    already_find_name_flag = 1
                elif 'option' in lines[i].lower() and 'summary' not in lines[i].lower():
                    section_name = self.__groff2Text(lines[i]).lower()
                    # already parse such option section
                    if already_find_option_flag == 1 and section_name in option_section_names:
                        parsing_type = ''
                        continue
                    parsing_type = "option"
                    already_find_option_flag = 1
                elif 'synopsis' in lines[i].lower():
                    # already done
                    if already_find_synopsis_flag == 1:
                        parsing_type = ''
                        continue
                    parsing_type = "synopsis"
                    already_find_synopsis_flag = 1
                elif 'description' in lines[i].lower():
                    # already done
                    if already_find_description_flag == 1:
                        parsing_type = ''
                        continue
                    parsing_type = "description"
                    already_find_description_flag = 1
                else:
                    parsing_type = ''
                continue
                
            if parsing_type == '':
                continue
            elif parsing_type == 'name':
                line = self.__parseLine(lines[i], 'desc')
                groff_data["description"] += '\n' + line
            # Options parsing start
            elif parsing_type == 'option':
                # Option will appear in the next line 
                if lines[i][:3] in ['.TP', '.PP', '.RS', '.sp']:
                    if infinding_option == 0 and current_option != '':
                        next_line = self.__parseLine(lines[i+1], 'opt')
                        next_line = self.__stripOpt(next_line)
                        if next_line == '' or ord(next_line[0]) not in [8722, 45]:
                            continue
                    infinding_option = 1
                    current_option = ''
                    continue
                elif lines[i][:3] == '.IP':
                    line_split = lines[i].split('"') 
                    if len(line_split) == 1 or line_split[1] == '':
                        continue
                    # Special Characters (e.g., jq.1), option may apear in the next line
                    if lines[i].split('"')[1].startswith("\\(") and lines[i].split('"')[1][2:4] in ["bu", "co", "ct", "dd", "de", "dg", "rs", "em", "hy", "rg", "rs", "sc", "ul", "==", ">=", "<=", "!=", "->", "<-", "+-"]:
                        infinding_option = 1
                        current_option = ''
                        continue
                    # Check if option appears in the same line
                    if  ('\\-' not in lines[i].split('.IP')[1] and '"-' not in lines[i].split('.IP')[1] and '-' not in lines[i].split('.IP')[1]):
                        continue
                    else:
                        line = self.__parseLine(lines[i], 'opt')
                        line = self.__stripOpt(line)
                        if line == '':
                            continue
                        # dash and unicode dash
                        elif ord(line[0]) in [8722, 45]:
                            current_option = line
                            # Already parsed
                            if current_option in groff_data["options"]:
                                current_option = ""
                                continue
                            infinding_option = 0
                            groff_data["options"][current_option] = ''
                elif infinding_option == 1:
                    line = self.__parseLine(lines[i], 'opt')
                    line = self.__stripOpt(line)
                    if not current_option:
                        if line == '':
                            continue
                        # dash and unicode dash
                        elif ord(line[0]) in [8722, 45]:
                            current_option = line
                            # Already parsed
                            if current_option in groff_data["options"]:
                                current_option = ""
                                continue
                            groff_data["options"][current_option] = ''
                            infinding_option = 0
                # Description parsing start
                else:
                    if current_option:
                        line = self.__parseLine(lines[i], 'opt')
                        groff_data["options"][current_option] += '\n' + line
            elif parsing_type == 'synopsis':
                line = self.__parseLine(lines[i], 'desc')
                groff_data["synopsis"] += '\n' + line
            elif parsing_type == 'description':
                line = self.__parseLine(lines[i], 'desc')
                groff_data["description"] += '\n' + line

        ret_data = {"description": self.__groff2Text(groff_data["description"]), "options": {}, "synopsis": self.__groff2Text(groff_data['synopsis'])}
        blank_opt_list = []
        for current_option in groff_data["options"]:
            desc = self.__groff2Text(groff_data["options"][current_option])
            if desc == "":
                blank_opt_list.append(current_option)
                continue
            if len(blank_opt_list) > 0:
                new_opt = "%s, %s" % (", ".join(blank_opt_list).strip(), current_option)
                blank_opt_list = []
            else:
                new_opt = current_option
            ret_data["options"][new_opt] = desc
        return prog_name.lower(), ret_data

    def __checkManVersion(self):
        cmd = "man -V"
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, shell=True)
        stdout, stderr = p.communicate()
        if shutil.which("man") is None:
            print("[x] Cannot find the 'man' command")
            exit(1)
        # For man in OSX
        if stderr:
            # Unknown man version
            if "illegal option -- V" in stderr:
                man_version = "Unknown"
            # man, version 1.6g
            else:
                man_version = stdout[13:].strip()
        else:
            man_version = stdout[4:].strip()
        return man_version

    def __groff2Text(self, groff):
        content = ".TH TEST\n.SH TEST\n%s" % groff

        with open("/tmp/test.1", "w") as f:
            f.write(content)
        
        cmd = "man /tmp/test.1 | col -b"
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, universal_newlines=True, shell=True)
        stdout, _ = p.communicate()

        output_lines = stdout.splitlines()[3:-1]
        output_lines = [item.strip() if item != "" else "\n" for item in output_lines]

        text = ' '.join(output_lines).strip()
        return text

    def __parseLine(self, raw_line, type=''):
        line = ' '
        raw_line = raw_line.strip()
        if raw_line == '':
            return line

        line = raw_line.strip()

        if type == "opt":
            line = self.__groff2Text(line)

        return line

    def __stripOpt(self, opt):
        opt = opt.strip("\"").strip()
        opt = re.sub(' +', ' ', opt)
        if opt == '':
            return ''
        while opt[-1] == ':':
            opt = opt[:-1]
            opt = opt.strip()

        i = 0
        new_opt = ''
        in_bracket = 0
        while i < len(opt):
            if i == 0 and opt[i] == '<':
                in_bracket = 1
            elif in_bracket == 1:
                if opt[i] == '>':
                    in_bracket = 0
                else:
                    new_opt += opt[i]
            else:
                new_opt += opt[i]
            i += 1
        return new_opt
    