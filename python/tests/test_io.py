import io
import random

from gpsvet import clean_track, read_csv, read_gpx, write_csv
from gpsvet.cli import main

GPX = """<?xml version="1.0"?>
<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1"
     xmlns:gpxtpx="http://www.garmin.com/xmlschemas/TrackPointExtension/v2">
  <trk><trkseg>
    <trkpt lat="52.1" lon="4.3"><ele>2.5</ele><time>2026-10-01T08:00:00Z</time><hdop>0.9</hdop>
      <extensions><gpxtpx:TrackPointExtension><gpxtpx:speed>1.4</gpxtpx:speed>
      <gpxtpx:course>90</gpxtpx:course></gpxtpx:TrackPointExtension></extensions></trkpt>
    <trkpt lat="52.1" lon="4.30002"><time>2026-10-01T08:00:01Z</time></trkpt>
  </trkseg></trk>
</gpx>"""


def test_csv_round_trip():
    fixes = clean_track("walk", 1, random.Random(0))
    buf = io.StringIO()
    write_csv(fixes, buf)
    buf.seek(0)
    assert read_csv(buf) == fixes


def test_csv_aliases_and_iso_time():
    data = "Latitude,Longitude,Timestamp,Bearing\n52.1,4.3,2026-10-01T08:00:00Z,90\n"
    (f,) = read_csv(io.StringIO(data))
    assert (f.lat, f.lon, f.t, f.course, f.speed) == (52.1, 4.3, 1790841600.0, 90.0, None)


def test_gpx_with_garmin_extensions():
    a, b = read_gpx(io.StringIO(GPX))
    assert (a.alt, a.hdop, a.speed, a.course) == (2.5, 0.9, 1.4, 90.0)
    assert b.t - a.t == 1 and b.speed is None


def test_cli_exit_code(tmp_path, capsys):
    p = tmp_path / "t.gpx"
    p.write_text(GPX)
    assert main([str(p), "--profile", "walk"]) == 0
    assert "ok" in capsys.readouterr().out
