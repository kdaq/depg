"""
DEPG Utility Library

Various helper functions:
 * `addr()`        : Convert a coord like B37 to formulas module style
 * `dict_to_list()`: Flatten a dict to a list
 * `get_cache()`   : Read JSON cache for quick loading
 * `get_config()`  : Read JSON config
"""

import json
import os


def addr(coord, sheet_name=None):
    """
    Given a coordinate, convert to formulas style.

    Parameters
    ----------
    coord: str
        Coordinate like ``B37``
    sheet_name: str, optional
        Like `PROFILE_GENERATOR`, only needed if cache was not generated yet

    Returns
    -------
    str
        A value like ``[PROFILE_GENERATOR.XLSX]PROFILE_GENERATOR!B37``
    """

    spreadsheet_file = get_config()["spreadsheet_file"]
    if not sheet_name:
        sheet_name = get_cache()["properties"]["sheet_name"]
    return "'[{}]{}'!{}".\
        format(spreadsheet_file.upper(), sheet_name.upper(), coord.upper())

def dict_to_list(d):
    """
    Flatten a dictionary to a one-dimensional list.

    Parameters
    ----------
    d: dict
        Any one-dimensional dict, e.g. ``{k1: v1, k2: v2}``

    Returns
    -------
    list
        A flattened list, e.g. ``[k1, v1, k2, v2]``
    """
    for k,v in d.items():
        yield k
        yield v

def get_cache(xl=None, wb=None):
    """
    Cache parts of the spreadsheet, including dropdown widgets.

    The formulas spreadsheet takes a long time to load, so cache enough details to render the initial page.

    If xl and wb are supplied, create or refresh cache.

    Parameters
    ----------
    xl: formulas.ExcelModel, optional
        The object created with the profile generator spreadsheet
    wb: openpyxl.workbook.workbook.Workbook, optional
        The internal workbook object, pulled from the xl object

    Returns
    -------
    cache_data: dict
        Data used to render index template
    """

    cache_data = {}

    cache_data_file = get_config()["cache_json"]
    if xl and wb:
        ws = wb.active
        sol = xl.calculate()

        sheet_name = wb.sheetnames[0]
        cache_data["properties"] = {
            "sheet_name": sheet_name,
            "created": str(wb.properties.created),
            "creator": wb.properties.creator,
            "last_modified_by": wb.properties.last_modified_by,
            "modified": str(wb.properties.modified),
        }

        # Pull out drop-down values using openpyxl
        cache_data["dropdown_data"] = {}
        for validation in ws.data_validations.dataValidation:
            ranges = validation.sqref.ranges
            list_cells = ws[validation.formula1]
            data_cell_coord = str(ranges[0])
            label_cell_coord = ws[data_cell_coord].offset(row=0, column=-1).coordinate
            category = sol[addr(label_cell_coord, sheet_name)].value[0,0]
            cache_data["dropdown_data"][data_cell_coord] = {
                "category": category,
                "values": [cell.value for cell_row in list_cells for cell in cell_row]
            }

        with open(cache_data_file, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=4)
    else:
        with open(cache_data_file) as f:
            cache_data = json.load(f)

    # Selected item will default to index 0
    for cat_data in cache_data["dropdown_data"].values():
        cat_data["selected_idx"] = 0

    return cache_data

def get_config():
    """
    Load config dict from config.json

    Returns
    -------
    config_d: dict
        Data used to config this app and render profiles
    """

    config_file = "config.json"
    if os.path.isfile(config_file):
        with open(config_file) as f:
            config_d = json.load(f)

    if not config_d:
        raise RuntimeError("Could not load config!")

    return config_d
