
import os
import sys
from datetime import datetime, timedelta
import json
import yaml
import surfex

outdir = "/lustre/storeB/project/nwp/H2O/wp2/forcing/v2/"
cfg_dir = "/home/trygveasp/met_nordic/cfg/"
workdir_path = "/lustre/storeB/project/nwp/H2O/wp2/forcing/v2_work/"


def recursive_sub(input1, search, val):
    # check whether it's a dict, list, tuple, or scalar
    if isinstance(input1, dict):
        items = input1.items()
    elif isinstance(input1, (list, tuple)):
        items = enumerate(input1)
    else:
        # just a value, split and return
        # print(input, search, val)
        # print(input, type(input))
        if isinstance(input1, str):
            if isinstance(val, str):
                ret = str(input1).replace(str(search), str(val))
            elif str(input1) == str(search):
                ret = val
            else:
                ret = input1
            return ret
        else:
            return input1

    # now call ourself for every value and replace in the input
    for key, value in items:
        input1[key] = recursive_sub(value, search, val)
    return input1


def merge_var_dict(merged_dict_copy, var_name, fmt, screen=False):
    merged_dict = merged_dict_copy.copy()
    var_dict = {}
    for key in merged_dict[fmt]:
        # print("format", key, merged_dict["netcdf"][key])
        var_dict.update({key: merged_dict[fmt][key]})

    # print("merged dict", merged_dict)
    v_dict = {}
    if var_name in merged_dict:
        if screen:
            if fmt in merged_dict[var_name]["screen"]:
                if "converter" in merged_dict[var_name]["screen"][fmt]:
                    if "none" in merged_dict[var_name]["screen"][fmt]["converter"]:
                        v_dict = merged_dict[var_name]["screen"][fmt]["converter"]["none"]
        else:
            if fmt in merged_dict[var_name]:
                if "converter" in merged_dict[var_name][fmt]:
                    if "none" in merged_dict[var_name][fmt]["converter"]:
                        v_dict = merged_dict[var_name][fmt]["converter"]["none"]

    # print(v_dict)
    for key in v_dict:
        # print("v_dict", key, v_dict[key])
        var_dict.update({key: v_dict[key]})

    return var_dict


def set_variable(merged_dict, var, fb, fmt, screen=False):
    var_dict = merge_var_dict(merged_dict.copy(), var, fmt, screen=screen)
    variable = surfex.variable.Variable(fmt, var_dict.copy(), fb)
    # print(variable.filepattern)
    return variable


def get_dict_val(merged_dict, var_name, name, fmt, screen=False):
    var_dict = merge_var_dict(merged_dict, var_name, fmt, screen=screen)
    if screen:
        val = var_dict[name]
    else:
        val = var_dict[name]
    return val


def set_dict_val(user_config, var_name, name, value, fmt, screen=False):

    if screen:
        user_config[var_name]["screen"][fmt]["converter"]["none"].update({name: value})
    else:
        user_config[var_name][fmt]["converter"]["none"].update({name: value})
    return user_config


def adjust_missing_files(config, merged_dict, var_name, validtime, fb, fmt, screen=False,
                         previoustime=None):

    variable = set_variable(merged_dict, var_name, fb, fmt, screen=screen)
    max_hours = 66
    for hour in range(0, max_hours):
        dtg = validtime - timedelta(hours=hour)
        if previoustime is not None:
            previoustime = dtg - timedelta(seconds=3600)

        fname = read_variable(variable, dtg, var_name, previoustime=previoustime)
        if fname is None:
            offset = get_dict_val(merged_dict, var_name, "offset", fmt, screen=screen)
            fcint = get_dict_val(merged_dict, var_name, "fcint", fmt, screen=screen)
            # Modify
            if offset < max_hours:
                offset = offset + 3600

            print(offset, fcint)
            merged_dict = set_dict_val(merged_dict, var_name, "offset", offset, fmt, screen=screen)
            merged_dict = set_dict_val(merged_dict, var_name, "fcint", fcint, fmt, screen=screen)
            variable = set_variable(merged_dict, var_name, fb, fmt, screen=screen)
        else:
            vtime = validtime.strftime("%Y%m%d%H")
            in_12_hours = (validtime + timedelta(hours=12)).strftime("%Y%m%d%H")

            if validtime != dtg:
                config.update({vtime: {"model_pattern": fname}})
                config.update({in_12_hours: {"model_pattern": variable.filepattern}})

            vtime = validtime.strftime("%Y%m%d%H")
            if vtime in config:
                print("using", fname, " for ", validtime)
                print(vtime, " -> ", config[vtime])
            return config
    raise Exception


def read_variable(variable, validtime, var_name, previoustime=None):
    # print(variable.filepattern)
    fname = check_existence(variable.get_filename(validtime=validtime, previoustime=previoustime), validtime, var_name)
    return fname


def get_args(config_file, dtg):
    print(datetime.strftime(dtg, "%Y%m%d%H"))
    user_config = json.load(open(cfg_dir + "/user_config.json"))
    config = json.load(open(cfg_dir + config_file))
    args = cfg_dir + "met_nordic.args"
    model_pattern = None
    met_nordic_pattern = None
    fb = None
    member = None

    ps_offset = 0
    ps_fcint = 21600
    acc_offset = 10800
    acc_fcint = 21600

    # print(config)
    config_name = "user_config"
    for config_dtg in config:
        cdtg = datetime.strptime(config_dtg, "%Y%m%d%H")
        if cdtg <= dtg:
            if "model_pattern" in config[config_dtg]:
                model_pattern = config[config_dtg]["model_pattern"]
            if "met_nordic_pattern" in config[config_dtg]:
                met_nordic_pattern = config[config_dtg]["met_nordic_pattern"]
            if "fb" in config[config_dtg]:
                fb = config[config_dtg]["fb"]
            if "member" in config[config_dtg]:
                member = config[config_dtg]["member"]
        if cdtg == dtg:
            if "config" in config[config_dtg]:
                config_name = config[config_dtg]["config"]
            if "ps_offset" in config[config_dtg]:
                ps_offset = config[config_dtg]["ps_offset"]
            if "ps_fcint" in config[config_dtg]:
                ps_fcint = config[config_dtg]["ps_fcint"]
            if "acc_offset" in config[config_dtg]:
                acc_offset = config[config_dtg]["acc_offset"]
            if "acc_fcint" in config[config_dtg]:
                acc_fcint = config[config_dtg]["acc_fcint"]

    if model_pattern is None:
        raise Exception("No model pattern found")
    if met_nordic_pattern is None:
        raise Exception("No met_nordic_pattern found")
    if fb is None:
        raise Exception("No fb found")

    if config_name != "user_config":
        print(config_name)
        if config_name == "only_forecast":
            args = cfg_dir + "only_forecast.args"
        elif config_name == "copy_old":
            args = cfg_dir + "copy_old.args"
    user_config = user_config[config_name]
    user_config = recursive_sub(user_config, "@model_pattern@", model_pattern)
    user_config = recursive_sub(user_config, "@met_nordic_pattern@", met_nordic_pattern)
    user_config = recursive_sub(user_config, "@member@", member)
    user_config = recursive_sub(user_config, "@ps_offset@", ps_offset)
    user_config = recursive_sub(user_config, "@ps_fcint@", ps_fcint)
    user_config = recursive_sub(user_config, "@acc_offset@", acc_offset)
    user_config = recursive_sub(user_config, "@acc_fcint@", acc_fcint)

    # print("get_args", user_config)
    return fb, args, user_config, config_name


def met_nordic_forcing(dtg, fh, logfile):
    dtg_str = datetime.strftime(dtg, "%Y%m%d%H")
    yyyy = datetime.strftime(dtg, "%Y")
    yy = datetime.strftime(dtg, "%y")
    mm = datetime.strftime(dtg, "%m")
    dd = datetime.strftime(dtg, "%d")
    hh = datetime.strftime(dtg, "%H")

    workdir = workdir_path + "/" + yyyy + "/" + mm + "/" + dd + "/"
    pysurfex = "/modules/centos7/user-apps/suv/pysurfex/0.0.1-dev/"
    output_path = outdir + "/" + yyyy + "/" + mm + "/" + dd + "/"

    fh.write("#!/bin/bash\n")
    fh.write("#$ -N " + "MN" + yy + mm + dd + hh + "\n")
    fh.write("#$ -pe shmem-1 1\n")
    fh.write("#$ -q research-el7.q\n")
    fh.write("#$ -l h_vmem=5G\n")
    fh.write("#$ -S /bin/bash\n")
    fh.write("#$ -M trygveasp@met.no\n")
    fh.write("#$ -m a\n")
    fh.write("#$ -o " + logfile + "\n")
    fh.write("#$ -e " + logfile + "\n")
    fh.write("\n")

    # Create work and output_path
    os.system("mkdir -p " + output_path)

    fh.write("# Load modules\n")
    fh.write("module load Python/3.7.3 gridpp/0.6.0 suv/pysurfex/0.0.1-dev\n\n")

    fb, args, user_config, config_name = get_args("config.json", dtg)

    yaml.dump(user_config, open(workdir + "user_config_" + dtg_str + ".yml", "w"),  default_flow_style=False)

    # print("fb", fb, type(fb))
    # print("args", args)
    # print("user_config", user_config)
    fh.write("# Create forcing \n")
    cmd = "create_forcing " + \
          " --options " + args + \
          " " + dtg_str + " " + dtg_str + \
          " -d " + pysurfex + "examples/domains/met_nordic.json" + \
          " -c " + workdir + "user_config_" + dtg_str + ".yml" + \
          " -of " + output_path + "FORCING_" + yyyy + mm + dd + "T" + hh + "Z.nc" + \
          " -fb " + str(fb)

    fh.write("echo " + cmd + "\n\n")
    fh.write(cmd + " || exit 1\n\n")

    fh.write("# Plot \n")
    variables = ["ZS", "Tair", "Qair", "PSurf", "DIR_SWdown", "SCA_SWdown", "LWdown", "Rainf", "Snowf", "Wind",
                 "Wind_DIR", "CO2air"]
    domain_file = pysurfex + "examples/domains/met_nordic.json"

    for var in variables:
        cmd = "plot_points " + \
              "--sfx_geo_input " + domain_file + \
              " -g " + domain_file + \
              " -i " + output_path + "FORCING_" + yyyy + mm + dd + "T" + hh + "Z.nc" \
              " -v " + var + \
              " -t " + dtg_str + \
              " --interpolator bilinear " + \
              " -o " + output_path + var + "_" + dtg_str + ".png"
        fh.write("echo " + cmd + "\n\n")
        fh.write(cmd + " || exit 1\n")


def time_loop(dtg_start, dtg_stop):

    dtg = dtg_start
    print(dtg, dtg_stop)
    while dtg <= dtg_stop:
        dtg_str = datetime.strftime(dtg, "%Y%m%d%H")
        yyyy = datetime.strftime(dtg, "%Y")
        mm = datetime.strftime(dtg, "%m")
        dd = datetime.strftime(dtg, "%d")
        hh = datetime.strftime(dtg, "%H")
        workdir = workdir_path + "/" + yyyy + "/" + mm + "/" + dd + "/"
        os.system("mkdir -p " + workdir)

        jobfile = workdir + "/met_nordic_forcing_" + dtg_str + ".job"
        logfile = workdir + "/met_nordic_forcing_" + dtg_str + ".log"

        output_file = outdir + "/" + yyyy + "/" + mm + "/" + dd + \
                               "/FORCING_" + yyyy + mm + dd + "T" + hh + "Z.nc"
        # print(output_file)
        if not os.path.exists(output_file):
            if os.path.exists(output_file + ".tmp"):
                os.system("rm " + output_file + ".tmp")
            fh = open(jobfile, "w")
            met_nordic_forcing(dtg, fh, logfile)
            fh.close()
            # print(jobfile)
            os.system("qsub -V -cwd " + jobfile)
        else:
            print(output_file + " exists")
        dtg = dtg + timedelta(seconds=3600)


def check_existence(fname, dtg, var):
    if not os.path.exists(fname):
        print("Missing ", fname, datetime.strftime(dtg, "%Y%m%d%H"), var)
        return None
    return fname


def check_loop(dtg_start, dtg_stop):

    dtg = dtg_start
    print(dtg, dtg_stop)
    config = json.load(open(cfg_dir + "main_config.json"))

    year = datetime.strftime(dtg, "%Y")
    while dtg <= dtg_stop:

        year2 = datetime.strftime(dtg, "%Y")
        if year2 != year:
            json.dump(config, open(cfg_dir + "config2_" + year + ".json", "w"), indent=2, sort_keys=True)
            year = year2
        vars_config = yaml.load(open("/home/trygveasp/revision_control/pysurfex/surfex/cfg/config.yml", "r"))
        fb, args, user_config, config_name = get_args("main_config.json", dtg)
        fb = datetime.strptime(fb, "%Y%m%d%H")
        merged_dict = surfex.deep_update(vars_config, user_config)

        fmt = "netcdf"
        if config_name == "copy_old":
            fmt = "surfex"
        if int(dtg.strftime("%H")) % 6 == 0:
            config = adjust_missing_files(config, merged_dict, "PS", dtg, fb, fmt)
        if config_name == "user_config":
            variable = set_variable(merged_dict, "TA", fb, fmt, screen=True)
            fname = read_variable(variable, dtg, "TA")
            if fname is None:
                raise Exception

        dtg = dtg + timedelta(hours=1)

    json.dump(config, open(cfg_dir + "config2.json", "w"), indent=2, sort_keys=True)


def check_missing_loop(dtg_start, dtg_stop):

    dtg = dtg_start
    print(dtg, dtg_stop)

    while dtg <= dtg_stop:
        print(dtg)
        yyyy = datetime.strftime(dtg, "%Y")
        mm = datetime.strftime(dtg, "%m")
        dd = datetime.strftime(dtg, "%d")
        hh = datetime.strftime(dtg, "%H")
        output_file = outdir + "/" + yyyy + "/" + mm + "/" + dd + \
                               "/FORCING_" + yyyy + mm + dd + "T" + hh + "Z.nc"
        # print(output_file)
        if not os.path.exists(output_file):
            print("Output file is missing: " + output_file)

        dtg = dtg + timedelta(hours=1)
