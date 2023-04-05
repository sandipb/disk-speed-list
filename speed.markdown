# List of disks

- [List of disks](#list-of-disks)
  - [Pen drives](#pen-drives)
    - [SanDisk 32GB Ultra Fit USB 3.1 Flash Drive - SDCZ430-032G-G46](#sandisk-32gb-ultra-fit-usb-31-flash-drive---sdcz430-032g-g46)

## Pen drives

### SanDisk 32GB Ultra Fit USB 3.1 Flash Drive - SDCZ430-032G-G46

<!-- markdownlint-disable-next-line -->
<img src="images/sandisk-ultra-fit.jpg" alt="sandisk ultra fit" width="300">

- Amazon: <https://www.amazon.ca/dp/B077VXV323>

```console
$ sudo lsusb -d 0781: -v|grep -e ^Bus -e bcd
Bus 004 Device 008: ID 0781:5583 SanDisk Corp. Ultra Fit
  bcdUSB               3.20
  bcdDevice            1.00

$ sudo hdparm -Tt --direct /dev/sda

/dev/sda:
 Timing O_DIRECT cached reads:   272 MB in  2.01 seconds = 135.20 MB/sec
 Timing O_DIRECT disk reads: 432 MB in  3.01 seconds = 143.71 MB/sec

$ sudo dd if=/dev/zero of=tempfile bs=4096 count=262144 conv=fdatasync status=progress
1073741824 bytes (1.1 GB, 1.0 GiB) copied, 41.1823 s, 26.1 MB/s

```
