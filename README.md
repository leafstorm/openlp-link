# OpenLP Link for Livestream Studio

This program is for churches that use [OpenLP][openlp] and
[Livestream Studio 6][ls6].
It maintains a CSV file in [Livestream Studio Certified Data Source][lscds]
format with the contents of your current OpenLP service item,
and switches slides in tandem with your media operator.
This lets you overlay lyrics, Bible verses, and custom slides on your video
feed while also projecting them to the congregation.

[openlp]: https://openlp.org/
[ls6]: https://livestream.com/studio
[lscds]: https://help.livestream.com/hc/en-us/articles/360002053948-Livestream-Studio-Certified-Data-Sources

## Instructions

1.  Download [a ZIP file of this code][zip] and unpack it.
2.  Install [Python][python] on your computer with Livestream Studio 6.
3.  Open a command prompt, type the command `pip install --user requests`,
    and press Enter.
4.  Turn on the OpenLP [Remote plugin][remote] in the [Plugin List][plugin].
5.  Run the `OpenLP Link.py` script in a command prompt.
    (On Windows you can just double-click the script.)
6.  Enter the URL from the Remote tab of the "Configure OpenLP" screen in
    the command prompt and press Enter. (After you connect once, it will
    remember the URL so that you can just press Enter.)
7.  Create a graphics layer with the "Import Layer > .CSV File" option.
    Choose the `Text Layer.csv` file that OpenLP Link created.
8.  Check "Watch file for update," "Use first row as column titles,"
    and "Read only."
9.  Set "Separators" to "Comma" and "Encoding" to "Auto."
10. Double-click the layer to enter the [GFX Designer][gfx], and add the
    "Body" and "Footer" fields to the graphics.
11. Enable the "Auto Push/Pull" option.

This repository also includes an example graphics layer that you can import.
It has all the correct options set, and a sample design to get started with.
However, you will need to change the file path to point to your
`Text Layer.csv` instead of the one included in the `.lsgfx` file.

If you set a fast enough transition (we use "Fade" over 5 frames),
it can change slides in less than a second even when OpenLP is running
on a different computer.
(In testing, it appears that using "Cut" actually makes it take longer,
which is odd.)

If the media operator blanks the screen in OpenLP -- either to black,
to theme, or to desktop -- OpenLP Link will also remove the text.
It will reappear when they unblank it.

While OpenLP Link is running, you can press Control-C in the command prompt
to temporarily disable the layer so that nothing displays.
If you press Control-C again, it will re-enable the layer after about a second.
To exit, press Control-C twice in a row.

If OpenLP Link loses connection to OpenLP, it will display the message
`(comm error, retrying!)` in the command prompt.
It will try to connect again every five seconds.

[zip]: https://github.com/leafstorm/openlp-link/archive/master.zip
[python]: https://www.python.org/downloads/
[remote]: https://manual.openlp.org/web_remote.html
[plugin]: https://manual.openlp.org/plugin_list.html
[gfx]: https://help.livestream.com/hc/en-us/articles/360002071247-Importing-Excel-Spreadsheets-and-CSV-Files

