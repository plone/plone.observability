Fix a race in the `plone_process_rss_peak_bytes` tests: they compared the metric
against a second `getrusage()` call, and the peak RSS could grow in between.
The tests now pin `getrusage()`.
