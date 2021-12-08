"""
Script for loading and formatting data.
"""

import pandas as pd
import numpy as np
from fredapi import Fred
from stats_can import StatsCan
import os
from time import sleep

food_categories = ["Bakery and cereal products (excluding baby food)",
                   "Dairy products and eggs",
                   "Fish, seafood and other marine products",
                   "Food purchased from restaurants",
                   "Food",
                   "Fruit, fruit preparations and nuts",
                   "Meat",
                   "Other food products and non-alcoholic beverages",
                   "Vegetables and vegetable preparations"]

regions = ["Canada"]


def load_fred(data_sources, api_key=None, min_date="1986-01-01", max_date=None, sleep_sec=0.5):
    """
    Load economic data using the FRED API.
    :param data_sources: A list of FRED series names to query.
    :param min_date: Date in YYYY-MM-DD format of earliest date requested, inclusive.
    :param max_date: Date in YYYY-MM-DD format of latest date requested, inclusive.
    :return: Economic data for the selected series and date ranges as a DataFrame.
    """
    all_series = {}
    fred = Fred(api_key=api_key)
    for index, source in enumerate(data_sources):
        try:
            sleep(sleep_sec)
            series = fred.get_series(source, min_date, max_date)
            series = series[series.index >= min_date]
            all_series[source] = series
            print(f"{source} loaded successfully, {index+1} of {len(data_sources)}.", end='\r')
        except Exception as e:
            print(e)
    all_df = pd.DataFrame(all_series)
    return all_df


def load_statscan(target_names, region='Canada', min_date="1986-01-01", max_date=None):
    """
    Load CPI data using the StatsCan API. Uses local storage to avoid excessive server requests.
    :param target_names: A list of the CPI target names.
    :param region: A geographical region, e.g. Canada, Ontario, etc.
    :param min_date: Date in YYYY-MM-DD format of earliest date requested, inclusive.
    :param max_date: Date in YYYY-MM-DD format of latest date requested, inclusive.
    :return: CPI data for the selected categories and date ranges as a DataFrame.
    """
    sc = StatsCan("./statscan_data")
    if len(sc.downloaded_tables) > 0:
        sc.update_tables()
    df = sc.table_to_df("18-10-0004-13")
    df = df.loc[df["GEO"] == region]
    all_target_data = {}
    for target_name in target_names:
        target_data = df.loc[df['Products and product groups'] == target_name]
        target_data = target_data[['REF_DATE', 'VALUE']]
        target_data.index = pd.to_datetime(target_data['REF_DATE'])
        target_data = target_data.drop('REF_DATE', axis=1)
        all_target_data[target_name] = target_data['VALUE']
    all_df = pd.DataFrame(all_target_data)
    if min_date is not None:
        all_df = all_df.loc[all_df.index >= min_date]
    if max_date is not None:
        all_df = all_df.loc[all_df.index <= max_date]
    return all_df


def preprocess_expl(expl_df, columns=None, interpolate=True, resample=None):
    if columns is None:
        columns = expl_df.columns
    if len(columns) < 1:
        return None
    if resample is not None:
        expl_df = expl_df.resample(resample).mean()
    if interpolate:
        expl_df = expl_df.interpolate()
        expl_df = expl_df.fillna(method='bfill')
    return expl_df[columns]


def preprocess_targets(targets_df, columns=None, interpolate=True,
                       resample=None, extend=1, extend_method='constant'):
    if columns is None:
        columns = targets_df.columns
    if extend > 0:
        if extend_method == 'constant':
            for _ in range(extend):
                row = pd.DataFrame(targets_df.iloc[-1]).T
                row.index = [targets_df.index[-1] + pd.DateOffset(months=1)]
                targets_df = targets_df.append(row)
        elif extend_method == 'project':
            for _ in range(extend):
                row = pd.DataFrame(targets_df.iloc[-1] + (targets_df.iloc[-1] - targets_df.iloc[-2])).T
                row = row.xs(0)
                row.name = targets_df.index[-1] + pd.DateOffset(months=1)
                targets_df = targets_df.append(row)
        else:
            print(f"extend_method: {extend_method} not recognized.")
    if resample is not None:
        targets_df = targets_df.resample(resample).mean()
    if interpolate:
        targets_df = targets_df.interpolate()
        targets_df = targets_df.fillna(method='bfill')
    return targets_df[columns]


def update_expl_data(data_sources, expl_filename, sleep_sec=0.5, api_key=None):
    if os.path.exists(expl_filename):
        # Update values for existing rows
        expl_df = pd.read_csv(expl_filename, index_col=0)
        expl_df.index = pd.to_datetime(expl_df.index)
        last_date = expl_df.index[-1]
        new_rows = load_fred(data_sources=expl_df.columns, min_date=last_date + pd.DateOffset(days=1), api_key=api_key, sleep_sec=sleep_sec)
        expl_df = expl_df.append(new_rows)
        # Add new columns, if necessary
        new_data_sources = [ds for ds in data_sources if ds not in expl_df.columns]
        new_df = load_fred(data_sources=new_data_sources, min_date=expl_df.index[0], max_date=expl_df.index[-1], api_key=api_key)
        if len(new_df.columns) > 0:
            expl_df = expl_df.join(new_df, how='right')
        expl_df.to_csv(expl_filename)
    else:
        expl_df = load_fred(data_sources=data_sources, max_date=None, api_key=api_key)
        expl_df.to_csv(expl_filename)
    return expl_df[data_sources]


def update_target_data(target_names, targets_filename):
    if os.path.exists(targets_filename):
        # Update values for existing rows
        targets_df = pd.read_csv(targets_filename, index_col=0)
        targets_df.index = pd.to_datetime(targets_df.index)
        last_date = targets_df.index[-1]
        new_rows = load_statscan(target_names=targets_df.columns, min_date=last_date + pd.DateOffset(days=1))
        targets_df = targets_df.append(new_rows)
        # Add new columns, if necessary
        new_target_names = [ds for ds in target_names if ds not in targets_df.columns]
        new_df = load_statscan(target_names=new_target_names,
                               min_date=targets_df.index[0],
                               max_date=targets_df.index[-1])
        if len(new_df.columns) > 0:
            targets_df = targets_df.join(new_df, how='right')
        targets_df.to_csv(targets_filename)
    else:
        targets_df = load_statscan(target_names=target_names, max_date=None)
        targets_df.to_csv(targets_filename)
    return targets_df[target_names]












































