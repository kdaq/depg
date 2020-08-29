#!/usr/bin/python3
"""
DEPG -- Decent Espresso Profile Generator

A simple web-based wrapper around the brilliant spreadsheet created by
Stéphane Ribes and Alwaysdialingin. Select parameters and generate a
profile, then upload it to your Decent Espresso machine.

To setup, download their spreadsheet from 
https://3.basecamp.com/3671212/buckets/7351439/messages/2607195024 and
drop it in the root dir of this project, named ``profile_generator.xlsx``.

If run directly, ``./depg.py`` will start a web server at port 8000.
Alternatively, starting via ``ENV="dev" ./depg.py`` will put the
application into development mode. This turns on Flask debugging and
starts at port 5001.

Recommended to run using a nginx proxy as described at 
https://flask.palletsprojects.com/en/1.1.x/deploying/wsgi-standalone/#proxy-setups.
"""

import decimal
import flask
import formulas
import formulas.functions.look
import json
import numpy as np
import os
import pprint
import tkinter

from flask import Blueprint
from flask import g
from flask import render_template
from flask import request
from formulas.functions import flatten,get_error,wrap_func,wrap_ufunc
from werkzeug.middleware.proxy_fix import ProxyFix

from util import addr, dict_to_list, get_cache, get_config 

# Instantiate web objects
bp = Blueprint('depg', __name__,
               template_folder='templates')

app = flask.Flask(__name__,
                  template_folder='templates')

app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)


@bp.route('/', methods=['GET'])
def index():
    """
    URL: `/`

    Main page with dropdown widgets from cached data.
    """

    cache_d = get_cache()
    return render_template('index.html', profile_title="DEPG", \
        dropdown_data=cache_d["dropdown_data"], properties=cache_d["properties"])


@bp.route('/', methods=['POST'])
def generate():
    """
    URL: `/`

    Use submitted values to generate a profile.
    """

    # Retain selected values
    profile_notes_list = []
    cache_d = get_cache()
    dropdown_data = cache_d["dropdown_data"]
    for coord, cat_data in dropdown_data.items():
        profile_notes_list.append("{}: {}".format(cat_data["category"], request.values.get(coord, "")))
        selected_value = request.values.get(coord, "")
        try:
            selected_index = cat_data["values"].index(selected_value)
        except ValueError:
            selected_index = 0
        cat_data["selected_idx"] = selected_index
    profile_notes = ", ".join(profile_notes_list)
    profile_title = request.values.get("profile_title")
    if not profile_title:
        profile_title = "DEPG"

    # Calculate params based on provided input
    sol = xl.calculate(
        inputs={addr(k): v for k, v in dict(request.values).items()}
    )

    # Pull out values we care about and round as needed
    result_d = {}
    for key, coord in get_config()["result_coords"].items():
        result_rounding = get_config()["result_rounding"][key]
        value = sol[addr(coord)].value[0,0]
        if result_rounding is not None:
            result_d[key] = round(decimal.Decimal(value), result_rounding)
        else:
            result_d[key] = value

    # Add profile_title, target weight, pressure peak, and shot time as well
    profile_notes += "\n\nPressure peak: {}, Stop at weight: {}, Time: {}" . \
        format(result_d["graph_pressure_peak"], result_d["graph_stop_on_weight"], result_d["graph_time"])
    result_d["profile_notes"] = profile_notes
    result_d["profile_title"] = profile_title

    # Fill in profile base and advanced steps
    base = {}
    for k,v in get_config()["profile"].items():
        if k == "advanced_shot":
            continue
        if type(v) is str:
            base[k] = v.format(**result_d)
        else:
            base[k] = v
    steps = []
    for raw_step in get_config()["profile"]["advanced_shot"]:
        step = {}
        for k,v in raw_step.items():
            if type(v) is str:
                step[k] = v.format(**result_d)
            else:
                step[k] = v
        steps.append(step)

    # Convert to TCL
    steps_tcl = [tkinter._stringify(list(dict_to_list(e))) for e in steps]
    profile = "advanced_shot {" + " ".join(steps_tcl) + "}\n"
    for k,v in base.items():
        profile += "{} {}\n".format(tkinter._stringify(k), tkinter._stringify(v))

    return render_template('index.html', profile_title=profile_title, \
        dropdown_data=cache_d["dropdown_data"], profile=profile, properties=cache_d["properties"])


if __name__ == "__main__":
    # Patches for formulas plugin
    #  - Define missing PRODUCT formula
    #  - Patch HLOOKUP and VLOOKUP to cast index to integer
    #  - Patch int to handle negatives properly
    FUNCTIONS = formulas.get_functions()
    FUNCTIONS['PRODUCT'] = wrap_func(lambda l: np.prod(list(flatten(l))))
    FUNCTIONS['HLOOKUP'] = wrap_ufunc(
        formulas.functions.look.xlookup, 
        input_parser=lambda val,vec,index,match_type=1,transpose=False: \
            formulas.functions.look._hlookup_parser(val,vec,int(index),match_type,\
            transpose),
        check_error=lambda *a: get_error(a[:1]), excluded={1, 2, 3}
    )
    FUNCTIONS['VLOOKUP'] = wrap_ufunc(
        formulas.functions.look.xlookup, 
        input_parser=lambda val,vec,index,match_type=1,transpose=True: \
            formulas.functions.look._hlookup_parser(val,vec,int(index),match_type,\
            transpose),
        check_error=lambda *a: get_error(a[:1]), excluded={1, 2, 3}
    )

    def _int(x, *args, **kwargs):
        ret = int(x, *args, **kwargs)
        if x < 0:
            ret -= 1
        return ret

    FUNCTIONS['INT'] = wrap_ufunc(_int)

    # Instantiate spreadsheet objects
    global xl
    xl = formulas.ExcelModel()
    wb, context = xl.add_book(get_config()["spreadsheet_file"])
    xl.pushes(*wb.worksheets, context=context)
    xl.finish()
    get_cache(xl, wb)

    app.register_blueprint(bp, url_prefix='/')
    if os.environ.get("ENV", "") == "dev":
        app.run(host='0.0.0.0', port=5001, debug=1)
    else:
        app.run(host='0.0.0.0', port=8000, debug=0)
