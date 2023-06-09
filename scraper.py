import pandas as pd
import requests
from bs4 import BeautifulSoup
from io import StringIO
from pandas import DataFrame
import urllib.parse
import datetime as dt
from tqdm import tqdm
from time import sleep


def get_playercount(appid: int = 730) -> dict:
    """
    Extracts current playercount from Steam API and 24-hour and all-time peak from steamcharts.com

    Parameters:
        appid (int): Steam appid. Defaults to 730 (CS:GO)
    Returns:
        dict: A dictionary with the current playercount, 24-hour peak and all-time peak
    """
    page = requests.get(
        f'https://steamcharts.com/app/{appid}')
    soup = BeautifulSoup(page.content, 'lxml')
    tag = soup.find('div', id='app-heading')
    tags = tag.find_all('div', class_="app-stat")
    result = {}
    result['24-hour peak'] = int(tags[1].find('span').string)
    result['All-time peak'] = int(tags[2].find('span').string)
    response = requests.get(
        f'https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/?appid={appid}')
    result['Playercount'] = response.json().get(
        'response', {}).get('player_count', 0)
    return result


def get_unboxing_numbers() -> DataFrame:
    """
    Extracts unboxing numbers from csgocasetracker.com

    Returns:
        DataFrame: A dataframe with total, monthly, weekly and daily unboxing number for every case
    """
    daily_response = requests.get(
        'https://csgocasetracker.com/calculations/calcDaily.csv')
    daily_csv = StringIO(daily_response.content.decode('utf-8'))
    weekly_response = requests.get(
        'https://csgocasetracker.com/calculations/calcWeekly.csv')
    weekly_csv = StringIO(weekly_response.content.decode('utf-8'))
    monthly_response = requests.get(
        'https://csgocasetracker.com/calculations/calculation.csv')
    monthly_csv = StringIO(monthly_response.content.decode('utf-8'))
    total_response = requests.get(
        'https://csgocasetracker.com/calculations/calculationTotal.csv')
    total_csv = StringIO(total_response.content.decode('utf-8'))
    daily_df = pd.read_csv(daily_csv, sep=',')
    weekly_df = pd.read_csv(weekly_csv, sep=',')
    monthly_df = pd.read_csv(monthly_csv, sep=',')
    total_df = pd.read_csv(total_csv, sep=',')
    result = pd.DataFrame()
    result['Case Name'] = total_df['Case Name']
    result['Total Unboxing Number'] = total_df['Unboxing Number']
    result['Monthly Unboxing Number'] = monthly_df['Unboxing Number']
    result['Weekly Unboxing Number'] = weekly_df['Unboxing Number']
    result['Daily Unboxing Number'] = daily_df['Unboxing Number']
    return result

# TODO: Add ability to change appid for price history functions


def get_price_history(item_name: str) -> DataFrame:
    """
    Extracts price history for a CS:GO/CS2 item from Steam

    Parameters:
        item_name(str): Name of the CS:GO/CS2 item on Steam Community Market
    Returns:
        DataFrame: A dataframe with price history containing datetimes, prices and amount sold for the given item
    """

    url = f"https://steamcommunity.com/market/listings/730/{urllib.parse.quote(item_name)}"
    response = requests.get(url).text
    response = response[response.find("line1")+6:]
    response = response[0:response.find("]];")+2]

    price_list = eval(response)
    month_list = [None,
                  'Jan',
                  'Feb',
                  'Mar',
                  'Apr',
                  'May',
                  'Jun',
                  'Jul',
                  'Aug',
                  'Sep',
                  'Oct',
                  'Nov',
                  'Dec']
    for i, entry in enumerate(price_list):
        # Date and time
        date_time = entry[0]
        date_time = date_time.split(" ")
        month = month_list.index(date_time[0])
        day = int(date_time[1])
        year = int(date_time[2])
        hour = int(date_time[3].split(":")[0])
        date_time = dt.datetime(
            year, month, day, hour=hour, minute=0, second=0)

        # Price
        price = float(entry[1])

        # Amount sold
        sold = int(entry[2])

        # compile dictionary and add it back to the list
        price_dict = {
            "Date": date_time,
            "Price(USD)": price,
            "Amount sold": sold
        }
        price_list[i] = price_dict

    df = pd.DataFrame.from_dict(price_list)

    return df


def smoothen_price_history(df: DataFrame) -> DataFrame:
    """
    Aggregates hourly values for the past month into daily values so that time gaps between all values are consistent.

    Parameters:
        DataFrame: A dataframe with price history acquired from price_history
    Returns:
        DataFrame: A dataframe with price history with average daily prices and total daily amounts sold for the last month
    """
    df_copy = df.copy()
    df_copy['Date'] = df_copy['Date'].apply(lambda x: x.date())
    df_copy = df_copy.groupby('Date', as_index=False).agg(
        {'Price(USD)': 'mean', 'Amount sold': 'sum'})
    return df_copy


def get_smooth_price_history(item_name: str) -> DataFrame:
    """
    Extracts price history for a CS:GO/CS2 item from Steam with values from the last month aggregated to have daily instead of hourly data

    Parameters:
        item_name(str): Name of the CS:GO/CS2 item on Steam Community Market
    Returns:
        DataFrame: A dataframe with price history containing dates, prices and amount sold for the given item
    """
    return smoothen_price_history(get_price_history(item_name))


def get_price_history_for_multiple(item_list: list[str], smoothen: bool = True, delay: int = 15) -> tuple[DataFrame, DataFrame]:
    """
    Extracts price history for a list of CS:GO/CS2 items from Steam

    Parameters:
        item_list(list[str]): Name of the CS:GO/CS2 item on Steam Community Market
        smoothen(bool): If True hourly values for the past month are aggregated into daily values so that time gaps between all values are consistent. Defaults to True
        delay(int): The delay between requests to Steam Community Market in seconds. Defaults to 15
    Returns:
        tuple[DataFrame, DataFrame]: A list containing two dataframes (amount sold history and price history) for the given list of items
    """

    df_list = []
    print("Getting info might take a while because of Steam rate limits")
    print("If this process fails, consider changing the delay between requests by setting the 'delay' parameter")
    print(f"Current delay is {delay} seconds")
    for item in tqdm(item_list):
        price_history = get_price_history(item)
        if smoothen:
            price_history = smoothen_price_history(price_history)
        df_list.append(price_history)
        sleep(delay)

    # Compile prices
    prices_df = pd.DataFrame()

    for item, df in zip(item_list, df_list):
        item_prices = df[['Date', 'Price(USD)']].copy()
        item_prices.rename(columns={'Price(USD)': item}, inplace=True)

        if prices_df.empty:
            prices_df = item_prices
        else:
            prices_df = prices_df.merge(item_prices, on='Date', how='outer')

    # Compile amounts sold
    amounts_df = pd.DataFrame()

    for item, df in zip(item_list, df_list):
        item_amounts = df[['Date', 'Amount sold']].copy()
        item_amounts.rename(columns={'Amount sold': item}, inplace=True)

        if amounts_df.empty:
            amounts_df = item_amounts
        else:
            amounts_df = amounts_df.merge(item_amounts, on='Date', how='outer')

    return prices_df, amounts_df


def get_historical_monthly_unboxing_numbers() -> DataFrame:
    """
    Extracts historical monthly unboxing numbers from csgocasetracker.com

    Returns:
        DataFrame: A dataframe with historical monthly unboxing numbers for every case
    """
    # Extracting stats
    csv_ids = ['january2022', 'february2022', 'march2022', 'april2022', 'may2022', 'june2022',
               'july2022', 'august2022', 'september2022', 'october2022', 'november2022',
               'december2022', 'january2023', 'february2023', 'march2023']
    df_list = []
    for id in csv_ids:
        response = requests.get(
            f'https://csgocasetracker.com/calculations/previousCalc/{id}.csv')
        csv = StringIO(response.content.decode('utf-8'))
        df = pd.read_csv(csv, sep=',')
        df_list.append(df)

    # Add a new column 'Month' in each dataframe to represent the month based on its position in the list
    for i, df in enumerate(df_list):
        df['Month'] = i + 1

    # Drop useless columns and merge the data
    df_list = [df[['Month', 'Case Name', 'Unboxing Number']] for df in df_list]
    df_concatenated = pd.concat(df_list)
    df_pivoted = df_concatenated.pivot(
        index='Case Name', columns='Month', values='Unboxing Number')
    df_pivoted.reset_index(inplace=True)

    # Make the cases to go in original order instead of alphabetical order
    case_names_order = df_list[-1]['Case Name'].values
    df_pivoted = df_pivoted.sort_values(by='Case Name', key=lambda x: x.map(
        {case: i for i, case in enumerate(case_names_order)}))

    df_pivoted.reset_index(drop=True, inplace=True)
    df_pivoted.fillna(0, inplace=True)
    df_transposed = df_pivoted.set_index('Case Name').transpose()
    df_transposed.index.name = None

    # Add a 'Month' column with month and year values as dates
    start_month = dt.date(2022, 1, 1)
    df_transposed['Month'] = [start_month +
                              pd.DateOffset(months=i) for i in range(len(df_transposed))]

    # Move the 'Month' column to be the first column in the dataframe
    cols = df_transposed.columns.tolist()
    cols = ['Month'] + cols[:-1]
    df_transposed = df_transposed[cols]

    return df_transposed


def montly_unboxing_numbers_to_daily(df: DataFrame) -> DataFrame:
    """
    Converts monthly historical unboxing numbers into daily numbers.

    Parameters:
        df(DataFrame): A dataframe with montly unboxing numbers acquired from get_historical_monthly_unboxing_numbers()
    Returns:
        DataFrame: A dataframe with historical daily unboxing numbers
    """
    df_result = df.copy()

    df_result['Month'] = pd.to_datetime(df_result['Month'])

    # Set 'Month' column as the index to use days_in_month attribute
    df_result.set_index('Month', inplace=True)
    df_result['Days in Month'] = df_result.index.days_in_month

    # Rescale values
    for col in df_result.columns[:-1]:
        df_result[col] = df_result[col] / df_result['Days in Month']
    df_result.drop('Days in Month', axis=1, inplace=True)

    # Expand the values so there's data for every day of each month and not only for the first day
    # These four lines are here so that we do not exclude the last month when filling in values
    last_date = df_result.index[-1]
    last_row = df_result.iloc[-1]
    last_row.name = last_date + pd.offsets.MonthEnd(0)
    df_result = pd.concat([df_result, pd.DataFrame(
        [last_row], columns=df_result.columns)])

    df_result = df_result.resample('D').ffill()

    df_result.reset_index(inplace=True)
    df_result.rename(columns={'index': 'Date'}, inplace=True)
    return df_result


def unboxing_moving_average(df: DataFrame, n: int = 30) -> DataFrame:
    """
    Applies a moving average to daily unboxing numbers 

    Parameters:
        df(DataFrame): A dataframe with daily unboxing numbers acquired from montly_unboxing_numbers_to_daily()
        n(int): Amount of days for the moving average. Defaults to 30
    Returns:
        DataFrame: A dataframe with smoothed historical daily unboxing numbers
    """
    df_ma = df.copy()
    df_ma.set_index('Date', inplace=True)
    df_ma = df_ma.rolling(f'{n}D').mean()
    df_ma.reset_index(inplace=True)
    return df_ma


def get_historical_daily_unboxing_numbers(n: int = 30) -> DataFrame:
    """
    Extracts historical monthly unboxing numbers from csgocasetracker.com, rescales them to
    get daily numbers and applies a moving average if needed.

    Parameters:
        n(int): Amount of days for the moving average. Defaults to 30
    Returns:
        DataFrame: A dataframe with historical daily unboxing numbers for every case
    """
    df = get_historical_monthly_unboxing_numbers()
    df = montly_unboxing_numbers_to_daily(df)
    df = unboxing_moving_average(df, n)
    return df


def update_with_recent_daily_numbers(df: DataFrame) -> DataFrame:
    """
    Updates historical daily unboxing numbers from csgocasetracker.com with recent values.

    Parameters:
        df(DataFrame): A dataframe with historical daily unboxing numbers for every case acquired from get_historical_daily_unboxing_numbers() or montly_unboxing_numbers_to_daily()
    Returns:
        DataFrame: A dataframe with historical daily unboxing numbers for every case up to today
    """

    df_expanded = df.copy()
    df_expanded.set_index('Date', inplace=True)

    # Expand the dataframe to include dates up to today
    last_date = df_expanded.index[-1] + pd.Timedelta(days=1)
    today = pd.Timestamp(dt.datetime.now().date())
    days_to_today = (today - last_date).days
    date_range = pd.date_range(last_date, periods=days_to_today + 1)
    df_expansion = df_expanded.reindex(date_range)
    df_expanded = pd.concat([df_expanded, df_expansion])

    # Fill in missing values
    df_recent = get_unboxing_numbers()
    for _, row in df_recent.iterrows():
        case_name = row['Case Name']

        last_month = df_expanded.index[-1] - pd.DateOffset(months=1)
        days_in_last_month = last_month.days_in_month
        monthly_unboxing = row['Monthly Unboxing Number'] / days_in_last_month
        weekly_unboxing = row['Weekly Unboxing Number'] / 7
        daily_unboxing = row['Daily Unboxing Number']

        df_expanded.loc[df_expanded.index[-1], case_name] = daily_unboxing
        df_expanded.loc[df_expanded.index[-7]:df_expanded.index[-1],
                        case_name] = df_expanded.loc[df_expanded.index[-7]:df_expanded.index[-1], case_name].fillna(weekly_unboxing)
        df_expanded.loc[last_month:, case_name] = df_expanded.loc[last_month:, case_name].fillna(
            monthly_unboxing)

    df_expanded.reset_index(inplace=True)
    df_expanded.rename(columns={'index': 'Date'}, inplace=True)

    return df_expanded
