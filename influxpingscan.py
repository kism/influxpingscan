#!/usr/bin/env python3
"""Ping scan network and send results to influxdb2"""

import socket
import time
import sys
import sqlite3
import configparser
import os
from sqlite3 import Error
from urllib.parse import quote


import requests
from ping3 import ping

PWD = os.path.abspath(os.path.dirname(os.path.realpath(__file__)))
CONFIG = configparser.ConfigParser()
CONFIG.read(f"{PWD}/settings.ini")

URL = CONFIG.get("INFLUXDB2", "url")
INFLUXDBTOKEN = CONFIG.get("INFLUXDB2", "token")
INFLUXDBBUCKET = CONFIG.get("INFLUXDB2", "bucket")
MEASUREMENT = CONFIG.get("INFLUXDB2", "measurement")
INFLUXDBORG = CONFIG.get("INFLUXDB2", "organization")
IPRANGE = CONFIG.get("NETWORK", "iprange")
DEBUG = CONFIG.get("PROGRAM", "debug")
if DEBUG.upper() == "TRUE":
    DEBUG = True
else:
    DEBUG = False

def print_debug(text, endchar):  # Debug messages in yellow if the debug global is true
    """My cring and basic debug colouring"""
    if DEBUG:
        print("\033[93m" + text + "\033[0m", end=endchar)


def scanhosts(conn):
    """Ping scan the network"""
    for i in range(1, 255):
        ip_address = IPRANGE + str(i)

        entry = None

        try:
            entry = socket.gethostbyaddr(ip_address)
        except socket.herror:
            pass

        timeepoch = int(time.time())

        if entry is not None:
            print("Found: " + entry[0] + " at IP address: " + ip_address)
            try:
                add_entry(conn, (entry[0], timeepoch))
            except sqlite3.IntegrityError:
                pass  # If the unique check fails, just move on
        else:
            print_debug("nothing at: " + ip_address, "\n")


def add_entry(conn, entry):
    """Add entry to the elo table"""
    sql = """ INSERT INTO hosts(hostname,lastalive)
            VALUES(?,?) """
    cur = conn.cursor()
    cur.execute(sql, entry)
    print("adding to database: " + str(entry))


def gethosts(conn):
    """Get existing list of hosts"""
    cur = conn.cursor()
    cur.execute("SELECT hostname FROM hosts")
    hostlist = cur.fetchall()
    # print(list)
    hostnamelist = []
    for hostname in hostlist:
        hostnamelist.append(hostname[0])
    print(hostnamelist)

    return hostnamelist


def checkhosts(conn):
    """ping all the hosts to see if they are up"""
    hostlist = gethosts(conn)
    timeepoch = int(time.time())
    # Since this scan takes a while, we put all the stats at the same time
    # to make the visual in grafana look better
    # timestamp = timeepoch * 1000000000
    timestamp = timeepoch

    data = ''

    for host in hostlist:
        pingresult = ping(host, timeout=0.5)
        print_debug('DEBUG ' + host + ' ' + str(pingresult), "\n")
        if pingresult is False:
            result = False
        else:
            result = True

        data = data + (
            "ping"
            + ","
            + "host=kg.lan"
            + ",lad="
            + host
            + " "
            + "value="
            + str(result)
            + " "
            + str(timestamp)
            + "\n"
        )

    url = (
        URL
        + "/api/v2/write?org="
        + quote(INFLUXDBORG)
        + "&bucket="
        + quote(INFLUXDBBUCKET)
        + "&precision=s"
    )

    print_debug('DEBUG ' + url + " \n" + data, "\n")

    try:
        req = requests.post(
            url,
            data=data,
            #headers={"Authorization": ("Token:" + INFLUXDBTOKEN)},
            headers={"Authorization": "Token " + INFLUXDBTOKEN},
            timeout=1,
        )
    except requests.exceptions.ConnectionError:
        pass

    print(req)












def create_connection(db_file):
    """Init to connect to db"""
    try:
        conn = sqlite3.connect(db_file)
        return conn
    except Error as err:
        print(err)
    return None


def create_table(conn, create_table_sql):
    """init to create table"""
    try:
        connection = conn.cursor()
        connection.execute(create_table_sql)
    except Error as err:
        print(err)


def main():
    """Init"""

    database = "hosts.db"
    databasepath = PWD + "/" + database

    sql_create_elo_table = """ CREATE TABLE IF NOT EXISTS hosts (
                                        hostname  text      PRIMARY KEY,
                                        lastalive int       NOT NULL
                                    ); """

    # create a database connection
    conn = create_connection(databasepath)
    if conn is None:
        print("Error! cannot create the database connection.")

    create_table(conn, sql_create_elo_table)  # keyword, create table

    if len(sys.argv) == 1:
        print("Give parameter pls")
    elif sys.argv[1] == "scan":
        scanhosts(conn)
    elif sys.argv[1] == "ping":
        checkhosts(conn)
    else:
        print("What have you done? try 'scan' or 'ping' as a parameter")

    conn.commit()


if __name__ == "__main__":
    main()
