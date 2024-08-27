#!/usr/bin/env python3
"""Ping scan network and send results to influxdb2"""

import socket
import time
import sys
import sqlite3
import configparser
import os
import logging
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

logging.basicConfig(level=logging.INFO)
if DEBUG.upper() == "TRUE":
    logging.basicConfig(level=logging.DEBUG)


def scan_hosts(conn):
    """Socket dns? scan the network"""
    remove_old_hosts(conn)
    # FIXME, haha
    for i in range(1, 255):
        ip_address = IPRANGE + str(i)

        entry = None

        try:
            entry = socket.gethostbyaddr(ip_address)
        except socket.error:
            pass

        timeepoch = int(time.time())

        if entry is not None:
            logging.info("Found: " + entry[0] + " at IP address: " + ip_address)
            try:
                add_entry(conn, (entry[0], timeepoch))
            except sqlite3.IntegrityError:
                pass  # If the unique check fails, just move on
        else:
            logging.debug("nothing at: " + ip_address, "\n")


def add_entry(conn, entry):
    """Add entry to the host table"""
    sql = """ INSERT INTO hosts(hostname,lastalive)
            VALUES(?,?) """
    cur = conn.cursor()
    cur.execute(sql, entry)
    logging.info("adding to database: " + str(entry))


def remove_old_hosts(conn):
    """Remove hosts that have been uncontactable for a week"""
    week_ago_time = int(time.time()) - (
        7 * 24 * 60 * 60
    )  # delete hosts older than a week
    cur = conn.cursor()

    cur.execute("SELECT hostname FROM hosts WHERE lastalive < ?", (week_ago_time,))
    hostlist = cur.fetchall()
    logging.info("Deleting: " + str(hostlist))

    cur.execute("DELETE FROM hosts WHERE lastalive < ?", (week_ago_time,))
    conn.commit()


def get_hosts(conn):
    """Get existing list of hosts"""
    cur = conn.cursor()
    cur.execute("SELECT hostname FROM hosts")
    hostlist = cur.fetchall()
    hostnamelist = []
    for hostname in hostlist:
        hostnamelist.append(hostname[0])
    logging.debug(hostnamelist)

    return hostnamelist


def check_hosts(conn):
    """ping all the hosts to see if they are up"""
    hostlist = get_hosts(conn)
    timeepoch = int(time.time())
    # Since this scan takes a while, we put all the stats at the same time
    # to make the visual in grafana look better
    # timestamp = timeepoch * 1000000000
    timestamp = timeepoch

    data = ""

    logging.info("pinging hosts")

    for host in hostlist:
        pingresult = None
        i = 0
        while not pingresult and i <= 3:
            pingresult = ping(host, timeout=0.5)
            logging.debug(host + " " + str(pingresult), "\n")
            logging.debug(type(pingresult))
            if pingresult is None or pingresult is False:
                result = False
                time.sleep(0.1)
            else:
                result = True
            i = i + 1

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

    logging.debug("POST " + url + " \n" + data, "\n")

    try:
        req = requests.post(
            url,
            data=data,
            # headers={"Authorization": ("Token:" + INFLUXDBTOKEN)},
            headers={"Authorization": "Token " + INFLUXDBTOKEN},
            timeout=1,
        )
        logging.debug(req)

    except requests.exceptions.ConnectionError:
        logging.error("Could not POST")
        sys.exit(1)


def create_connection(db_file):
    """Init to connect to db"""
    try:
        conn = sqlite3.connect(db_file)
        return conn
    except Error as err:
        logging.error(err)
    return None


def create_table(conn, create_table_sql):
    """init to create table"""
    try:
        connection = conn.cursor()
        connection.execute(create_table_sql)
    except Error as err:
        logging.error(err)


def main():
    """Init"""

    database = "hosts.db"
    databasepath = PWD + "/" + database

    sql_create_host_table = """ CREATE TABLE IF NOT EXISTS hosts (
                                        hostname  text      PRIMARY KEY,
                                        lastalive int       NOT NULL
                                    ); """

    # create a database connection
    conn = create_connection(databasepath)

    create_table(conn, sql_create_host_table)  # keyword, create table

    if len(sys.argv) == 1:
        logging.error("Give parameter pls")
    elif sys.argv[1] == "scan":
        scan_hosts(conn)
    elif sys.argv[1] == "ping":
        check_hosts(conn)
    else:
        logging.error("What have you done? try 'scan' or 'ping' as a parameter")

    conn.commit()


if __name__ == "__main__":
    main()
