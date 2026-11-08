-- Claims are partitioned by loss year so old years can be switched out to the archive.
CREATE PARTITION FUNCTION pf_ClaimsByYear (DATE)
    AS RANGE RIGHT FOR VALUES ('2019-01-01', '2020-01-01', '2021-01-01', '2022-01-01', '2023-01-01', '2024-01-01', '2025-01-01', '2026-01-01');
CREATE PARTITION SCHEME ps_ClaimsByYear AS PARTITION pf_ClaimsByYear ALL TO ([PRIMARY]);
