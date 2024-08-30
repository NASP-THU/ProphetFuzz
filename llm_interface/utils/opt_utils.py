import re

class OptionUtils:
    def __init__(self) -> None:
        pass

    def findAllOptions(self, string):
        return re.findall("-{1,2}[a-z0-9A-Z-_*=?!]+", string)
    
    def checkValuedField(self, opt):
        return bool(re.match("-{1,2}[a-z0-9A-Z-_*?!]+[=\[<\t: ]", opt))

    def removeValueField(self, opt):
        # -a=xxx, -a[xxxx], -a<xxxx>, -a xxx, -a:xxx
        return re.split("=|\[|<| |\t|:", opt.strip())[0]

    def splitJointOption(self, opt):
        splitted_opt_set = set()
        
        # "or" and "and" works like ", "
        opt = opt.replace(" or ", ", ").replace(" and ", ", ")
        # replace pattern like "-w --warning" and "-w (--warning)", ensure each option splitted by colon
        opt = re.sub("(-{1,2}[a-z0-9A-Z-*=?!]+) +(?=-{1,2}[a-z0-9A-Z-*=?!]+)", r"\1, ", opt).strip()
        opt = re.sub("\s*\((-{1,2}[a-z0-9A-Z-*=?!]+)\)", r", \1", opt).strip()
        # Several options are put together (, / |)
        for splitted_opt in re.split('\s*(?:\||,|/)\s*(?=-{1,2}[a-z0-9A-Z-*=?!]+)', opt):
            splitted_opt_set.add(splitted_opt.strip())
        
        return list(splitted_opt_set)
    
    def findPotentialOptionKeys(self, opt, key_mapping_dict):
        key_set = set()
        # First try to match the longest sub string of the entire opt
        for key in key_mapping_dict.keys():
            if re.match(r'^' + re.escape(opt) + r'(?![A-Za-z0-9_])', key):
                key_set.add(key_mapping_dict[key])
                break
        # Then try to match the longest sub string of opt without value
        if len(key_set) == 0:
            new_key = self.removeValueField(opt)
            if new_key == "":
                return []
            # --replace-*
            if new_key[-1] == "*":
                pattern = r'^' + re.escape(new_key[:-1]) + '.*$'
            else:
                pattern = r'^' + re.escape(new_key) + r'(?![A-Za-z0-9_])'
            for key in key_mapping_dict.keys():
                if re.match(pattern, key):
                    key_set.add(key_mapping_dict[key])
                    break
        # Cannot find the key of opt
        if len(key_set) == 0:
            # print(f"[Warn] Cannot find the name of {opt}")
            return []
        return list(key_set)
    
    def getKeyMappingDict(self, option_data):
        key_mapping_dict = {}
        for key in option_data:
            for opt in self.splitJointOption(key):
                key_mapping_dict[opt] = key
        return key_mapping_dict
