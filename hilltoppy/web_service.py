# -*- coding: utf-8 -*-
"""
Created on Tue May 29 10:12:11 2018

@author: MichaelEK
"""

#try:
#    from lxml import etree as ET
#except ImportError:
try:
    import xml.etree.cElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET
import requests
import pandas as pd
import numpy as np

### Parameters

available_requests = ['SiteList', 'MeasurementList', 'GetData']


### Functions


def build_url(base_url, hts, request, site=None, measurement=None, from_date=None, to_date=None, location=False, site_parameters=None, agg_method=None, agg_interval=None, alignment=None):
    """
    Function to generate the Hilltop url for the web service.

    Parameters
    ----------
    base_url : str
        root url str. e.g. http://wateruse.ecan.govt.nz
    hts : str
        hts file name including the .hts extension. Even if the file to be accessed is a dsn file, it must still have an hts extension for the web service.
    request : str
        The function request.
    site : str or None
        The site to be extracted.
    measurement : str or None
        The measurement type name.
    from_date : str or None
        The start date in the format 2001-01-01. None will put it to the beginning of the time series.
    to_date : str or None
        The end date in the format 2001-01-01. None will put it to the end of the time series.
    location : bool
        Should the location be returned? Only applies to the SiteList request.
    site_parameters : list
        A list of the site parameters to be returned with the SiteList request.
    agg_method : str
        The aggregation method to resample the data. e.g. Average, Total, Moving Average, Extrema.
    agg_interval : str
        The aggregation interval for the agg_method. e.g. '1 day', '1 week', '1 month'.

    Returns
    -------
    str
        URL string for the Hilltop web server.
    """

    ### Check base parameters

    if not base_url.endswith('/'):
        base_url = base_url + '/'
    if not hts.endswith('.hts'):
        raise ValueError('The hts file must end with .hts')
    if request not in available_requests:
        raise ValueError('request must be one of ' + str(available_requests))

    ### Make the first part of the url
    url = base_url + hts + '?Service=Hilltop&Request=' + request

    ### Ready the others
    if isinstance(site, (int, float, str)):
        url = url + '&Site=' + requests.utils.quote(str(site))
    if isinstance(measurement, str):
        url = url + '&Measurement=' + requests.utils.quote(measurement)
#    if isinstance(collection, str):
#        url = url + '&Collection=' + requests.utils.quote(collection)
    if isinstance(site_parameters, list):
        url = url + '&SiteParameters=' + requests.utils.quote(','.join(site_parameters))
    if location and (request == 'SiteList'):
        url = url + '&Location=Yes'

    ### Time interval goes last!
    if request == 'GetData':
        if isinstance(agg_method, str):
            url = url + '&Method=' + requests.utils.quote(agg_method)
        if isinstance(agg_interval, str):
            url = url + '&Interval=' + requests.utils.quote(agg_interval)
        if isinstance(from_date, str):
            url = url + '&TimeInterval=' + from_date
        else:
            url = url + '&TimeInterval=1800-01-01'
        if isinstance(to_date, str):
            url = url + '/' + to_date
        else:
            url = url + '/now'
        if isinstance(alignment, str):
            url = url + '&Alignment=' + alignment

    ### return
    return url


def site_list(base_url, hts):
    """
    SiteList request function. Returns a list of sites associated with the hts file.

    Parameters
    ----------
    base_url : str
        root url str
    hts : str
        hts file name including the .hts extension.

    Returns
    -------
    list of str
    """
    url = build_url(base_url, hts, 'SiteList')
    resp = requests.get(url)
    tree1 = ET.fromstring(resp.content)
    sites = [i.attrib['Name'] for i in tree1.findall('Site')]

    return sites


def measurement_list(base_url, hts, site, measurement=None, output_bad_sites=False):
    """
    Function to query a Hilltop server for the measurement summary of a site.

    Parameters
    ----------
    base_url : str
        root url str. e.g. http://wateruse.ecan.govt.nz
    hts : str
        hts file name including the .hts extension. Even if the file to be accessed is a dsn file, it must still have an hts extension for the web service.
    site : str or None
        The site to be extracted.
    measurement : str or None
        The measurement type name.
    output_bad_sites : bool
        Should sites with problems be returned?

    Returns
    -------
    DataFrame
        indexed by Site and Measurement.
        If output_bad_sites is True than two DataFrames are returned.
    """
    ds_types = ['DataType', 'From', 'To', 'SensorGroup']
    m_types = ['RequestAs', 'Units']

    ### Make url
    url = build_url(base_url, hts, 'MeasurementList', site, measurement)

    ### Request data and load in xml
    resp = requests.get(url)
    tree1 = ET.fromstring(resp.content)
    if tree1.find('Error') is not None:
        raise ValueError('No results returned from URL request')
    data_sources = tree1.findall('DataSource')
    if not data_sources:
        print('No data, returning empty DataFrame')
        return pd.DataFrame()

    ### Test to see if the site only has a WQ Sample and no other measurment
    if len(data_sources) == 1:
        d = data_sources[0]
        if d.attrib['Name'] == 'WQ Sample':
            print('Site only has WQ Sample')
            if output_bad_sites:
                return pd.DataFrame(), pd.DataFrame()
            else:
                return pd.DataFrame()

    ### Extract data into DataFrame
    data_list = []

    for d in data_sources:
        if d.find('TSType') is None:
            pass
        elif d.find('TSType').text != 'StdSeries':
            continue
        ds_dict = {c.tag: c.text.encode('ascii', 'ignore').decode() for c in d if c.tag in ds_types}
        m_all = d.findall('Measurement')
        for m in m_all:
            m_dict = {c.tag: c.text.encode('ascii', 'ignore').decode() for c in m if c.tag in m_types}
            m_dict.update(ds_dict)
            data_list.append(m_dict)

    mtype_df = pd.DataFrame(data_list)
    if not mtype_df.empty:
        mtype_df.rename(columns={'RequestAs': 'Measurement'}, inplace=True)
        if 'To' in mtype_df.columns:
            mtype_df.To = pd.to_datetime(mtype_df.To, infer_datetime_format=True, errors='coerce')
        if 'From' in mtype_df.columns:
            mtype_df.From = pd.to_datetime(mtype_df.From, infer_datetime_format=True, errors='coerce')
        if 'Units' in mtype_df.columns:
            mtype_df = mtype_df.replace({'Units': {'%': np.nan}}).copy()
        mtype_df['Site'] = site

        if output_bad_sites:
            bad_sites = mtype_df[mtype_df['From'].isnull() | mtype_df['To'].isnull() | (mtype_df['From'] < '1900-01-01') | (mtype_df['To'] > pd.Timestamp.today())]

            if bad_sites.empty:
                return mtype_df.set_index(['Site', 'Measurement']), pd.DataFrame()
            else:
                print('There are ' + str(len(bad_sites)) + ' sites with bad times')
    #            print(bad_sites)
                mtype_df = mtype_df[~(mtype_df['From'].isnull() | mtype_df['To'].isnull() | (mtype_df['From'] < '1900-01-01') | (mtype_df['To'] > pd.Timestamp.today()))]
                return mtype_df.set_index(['Site', 'Measurement']), bad_sites
        else:
            return mtype_df.set_index(['Site', 'Measurement'])

    else:
        if output_bad_sites:
            return pd.DataFrame(), pd.DataFrame()
        else:
            return pd.DataFrame()


def measurement_list_all(base_url, hts):
    """
    Function to query a Hilltop server for the measurement summary of all sites in an hts file.

    Parameters
    ----------
    base_url : str
        root url str. e.g. http://wateruse.ecan.govt.nz
    hts : str
        hts file name including the .hts extension. Even if the file to be accessed is a dsn file, it must still have an hts extension for the web service.

    Returns
    -------
    DataFrame
        indexed by Site and Measurement
    """
    sites = site_list(base_url, hts)

    mtype_list = []
    for s in sites:
#        print(s)
        m1 = measurement_list(base_url, hts, s)
        mtype_list.append(m1)
    mtype_df = pd.concat(mtype_list)

    return mtype_df


def get_data(base_url, hts, site, measurement, from_date=None, to_date=None, agg_method=None, agg_interval=None, alignment='00:00', parameters=False):
    """
    Function to query a Hilltop web server for time series data associated with a Site and Measurement.

    Parameters
    ----------
    base_url : str
        root url str. e.g. http://wateruse.ecan.govt.nz
    hts : str
        hts file name including the .hts extension. Even if the file to be accessed is a dsn file, it must still have an hts extension for the web service.
    request : str
        The function request.
    site : str or None
        The site to be extracted.
    measurement : str or None
        The measurement type name.
    from_date : str or None
        The start date in the format 2001-01-01. None will put it to the beginning of the time series.
    to_date : str or None
        The end date in the format 2001-01-01. None will put it to the end of the time series.
    agg_method : str
        The aggregation method to resample the data. e.g. Average, Total, Moving Average, Extrema.
    agg_interval : str
        The aggregation interval for the agg_method. e.g. '1 day', '1 week', '1 month'.
    parameters : bool
        Should the additional parameters (other than the value) be extracted and returned if they exist?

    Returns
    -------
    DataFrame
        If parameters is False, then only one DataFrame is returned indexed by Site, Measurement, and DateTime. If parameters is True, then two DataFrames are returned. The first is the same as if parameters is False, but the second contains those additional parameters indexed by Site, Measurement, DateTime, and Parameter.
    """
    ### Make url
    url = build_url(base_url=base_url, hts=hts, request='GetData', site=site, measurement=measurement, from_date=from_date, to_date=to_date, agg_method=agg_method, agg_interval=agg_interval, alignment=alignment)

    ### Request data and load in xml
    resp = requests.get(url)
    tree1 = ET.fromstring(resp.content)
    if tree1.find('Error') is not None:
        raise ValueError('No results returned from URL request')
    meas1 = tree1.find('Measurement')
    if meas1 is None:
        print('No data, returning empty DataFrame')
        return pd.DataFrame()
    datatype = meas1.find('DataSource').find('DataType').text
    data1 = meas1.find('Data')
    es1 = data1.getchildren()

    ### Extract data
    if measurement == 'WQ Sample':
        tsdata_dict = {}
        for d in es1:
            time1 = d.find('T').text
            params1 = d.findall('Parameter')
            if not params1:
                continue
            p_dict = {i.attrib['Name'].encode('ascii', 'ignore').decode(): i.attrib['Value'][:299].encode('ascii', 'ignore').decode() for i in params1}
            tsdata_dict.update({time1: p_dict})
        data_df = pd.DataFrame.from_dict(tsdata_dict, orient='index').stack().reset_index()
        data_df.columns = ['DateTime', 'Parameter', 'Value']
    elif datatype == 'WQData':
        if parameters:
            tsdata_list = []
            tsextra_dict = {}
            for d in es1:
                time1 = d.find('T').text
                value1 = d.find('Value').text.encode('ascii', 'ignore').decode()
                params1 = d.findall('Parameter')
                if params1:
                    p_dict = {i.attrib['Name'].encode('ascii', 'ignore').decode(): i.attrib['Value'][:299].encode('ascii', 'ignore').decode() for i in params1}
                    tsextra_dict.update({time1: p_dict})
                tsdata_list.append([time1, value1])
            data_df = pd.DataFrame(tsdata_list, columns=['DateTime', 'Value'])
            if tsextra_dict:
                extra_df = pd.DataFrame.from_dict(tsextra_dict, orient='index').stack().reset_index()
                extra_df.columns = ['DateTime', 'Parameter', 'Value']
        else:
            tsdata_list = []
            gap = 0
            for d in es1:
                tag1 = d.tag
                if tag1 == 'Gap':
                    gap = gap + 1
                    continue
                if gap % 2 == 1:
                    continue
                tsdata_list.append([d.find('T').text, d.find('Value').text.encode('ascii', 'ignore').decode()])
            data_df = pd.DataFrame(tsdata_list, columns=['DateTime', 'Value'])
    elif datatype in ['SimpleTimeSeries', 'MeterReading']:
        tsdata_list = []
        gap = 0
        for d in es1:
            tag1 = d.tag
            if tag1 == 'Gap':
                gap = gap + 1
                continue
            if gap % 2 == 1:
                continue
            tsdata_list.append([d.find('T').text, d.find('I1').text.encode('ascii', 'ignore').decode()])
        data_df = pd.DataFrame(tsdata_list, columns=['DateTime', 'Value'])
        data_df.Value = pd.to_numeric(data_df.Value, errors='ignore')


    ### Add in additional columns and convert DateTime
    data_df['DateTime'] = pd.to_datetime(data_df['DateTime'], infer_datetime_format=True)
    data_df['Site'] = site
    if measurement == 'WQ Sample':
        data_df = data_df.set_index(['Site', 'Parameter', 'DateTime'])
    else:
        data_df['Measurement'] = measurement
        data_df = data_df.set_index(['Site', 'Measurement', 'DateTime'])

    if (parameters) & (datatype == 'WQData'):
        if tsextra_dict:
            extra_df['DateTime'] = pd.to_datetime(extra_df['DateTime'], infer_datetime_format=True)
            extra_df['Measurement'] = measurement
            extra_df['Site'] = site
            extra_df = extra_df.set_index(['Site', 'Measurement', 'Parameter', 'DateTime'])

            return data_df, extra_df
        else:
            extra_df = pd.DataFrame(columns=['Site', 'Measurement', 'Parameter', 'DateTime', 'Value'])
            extra_df = extra_df.set_index(['Site', 'Measurement', 'Parameter', 'DateTime'])
            return data_df, extra_df
    else:
        return data_df


def wq_sample_parameter_list(base_url, hts, site):
    """
    Function to query a Hilltop server for the WQ sample parameter summary of a site.

    Parameters
    ----------
    base_url : str
        root url str. e.g. http://wateruse.ecan.govt.nz
    hts : str
        hts file name including the .hts extension. Even if the file to be accessed is a dsn file, it must still have an hts extension for the web service.
    site : str or None
        The site to be extracted.

    Returns
    -------
    DataFrame
        indexed by Site and Parameter
    """
    ### Make url
    url = build_url(base_url, hts, 'GetData', site, 'WQ Sample')

    ### Request data and load in xml
    resp = requests.get(url)
    tree1 = ET.fromstring(resp.content)
    if tree1.find('Error') is not None:
        raise ValueError('No results returned from URL request')
    meas1 = tree1.find('Measurement')
    if meas1 is None:
        print('No data, returning empty DataFrame')
        return pd.DataFrame()
    data1 = meas1.find('Data')
    es1 = data1.getchildren()

    ### Extract data
    tsdata_dict = {}
    p_set = set()
    for d in es1:
        params1 = d.findall('Parameter')
        if not params1:
            continue
        p_tup = tuple(i.attrib['Name'].encode('ascii', 'ignore').decode() for i in params1)
        tsdata_dict[d.find('T').text] = p_tup
        p_set.update(set(p_tup))
    p_t_dict = {p: tuple(i for i, k in tsdata_dict.items() if p in k) for p in p_tup}
    min_max_dict = {i: (min(k), max(k))  for i, k in p_t_dict.items()}
    mtype_df = pd.DataFrame.from_dict(min_max_dict, orient='index').reset_index()
    if not mtype_df.empty:
        mtype_df.columns = ['Parameter', 'From', 'To']
        mtype_df.To = pd.to_datetime(mtype_df.To, infer_datetime_format=True)
        mtype_df.From = pd.to_datetime(mtype_df.From, infer_datetime_format=True)
        mtype_df['DataType'] = 'WQSample'
        mtype_df['Site'] = site

    return mtype_df.set_index(['Site', 'Parameter'])



