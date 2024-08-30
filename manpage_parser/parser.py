import os
import re
import sys
import json
import argparse
from utils.groff_utils import GroffUtil

current_path = sys.path[0]
output_path = os.path.join(current_path, "output")

groff_util = GroffUtil()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='''
        %s - parse Groff file and save as json file.
    ''' % sys.argv[0], formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('--file', type=str, help = 'Input manpage file (groff format).', required=True)

    args = parser.parse_args()

    input_path = args.file

    # Parsing groff file
    program, groff_data = groff_util.parseGroff(input_path)
    
    with open(os.path.join(output_path, "manpage_%s.json" % program), "w") as f:
        f.write(json.dumps(groff_data)) 
