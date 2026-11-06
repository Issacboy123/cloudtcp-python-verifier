"""Explicit TCP-W1-1 citation metadata in extracted-document order.

The Markdown extraction is a human-readable reference, not runtime configuration.
Tests verify these entries against its headings and citation text. Update this
module and the reference together when changing extracted provisions.
"""


W1_SECTIONS = (
    ('SIGN-01', (
        'GUIDANCE',
        'Advance warning spacing (Table 6B-1)',
        'Table 6B-1; Sec. 6B.04 ¶07, p. 773',
    )),
    ('SIGN-02', (
        'GUIDANCE',
        'Urban nearest warning sign 4S-8S',
        'Sec. 6B.04 ¶04, p. 771',
    )),
    ('SIGN-03', (
        'GUIDANCE',
        'Rural first warning 8S-12S and 1500 ft open highway',
        'Sec. 6B.04 ¶06, p. 771',
    )),
    ('SIGN-04', (
        'OPTION',
        'Single-sign advance area 100 ft',
        'Sec. 6B.04 ¶05, p. 771',
    )),
    ('SIGN-05', (
        'GUIDANCE',
        'Freeway advance 1/2 mile',
        'Sec. 6B.04 ¶03, p. 771',
    )),
    ('SIGN-06', (
        'GUIDANCE',
        'Table 6B-1 field adjustments',
        'Sec. 6B.04 ¶07-09, p. 771',
    )),
    ('SIGN-07', (
        'GUIDANCE',
        'Closest sign 100 ft urban to 1000+ freeway',
        'Sec. 6H.02 ¶01, p. 798',
    )),
    ('SIGN-08', (
        'GUIDANCE',
        'ROAD WORK AHEAD first upstream',
        'Sec. 6H.02 ¶02, p. 798',
    )),
    ('SIGN-09', (
        'GUIDANCE',
        'Crossroad/driveway warning',
        'Sec. 6H.03 ¶02, p. 802',
    )),
    ('SIGN-10', (
        'GUIDANCE',
        'ROAD WORK on work road',
        'Sec. 6H.03 ¶01, p. 802',
    )),
    ('SIGN-11', (
        'GUIDANCE',
        'Signs on right-hand side',
        'Sec. 6F.02 ¶01, p. 789',
    )),
    ('SIGN-12', (
        'OPTION',
        'Both sides / portable / barricade mounting',
        'Sec. 6F.02 ¶02, p. 789',
    )),
    ('SIGN-13', (
        'STANDARD',
        'Rural mounting height 5 ft',
        'Sec. 6F.02 ¶04; Fig. 6F-1A, p. 789',
    )),
    ('SIGN-14', (
        'STANDARD',
        'Urban/sidewalk mounting height 7 ft',
        'Sec. 6F.02 ¶05-06; Fig. 6F-1C,D, p. 790',
    )),
    ('SIGN-15', (
        'STANDARD',
        'Portable support 1 ft; secondary -1 ft option',
        'Sec. 6F.02 ¶07-08, p. 790',
    )),
    ('SIGN-16', (
        'GUIDANCE',
        'Lateral offsets Fig 6F-1',
        'Fig. 6F-1 (Sec. 6F.02), p. 790',
    )),
    ('SIGN-17', (
        'GUIDANCE',
        'No supports on sidewalks/bike; ADA',
        'Sec. 6F.02 ¶09-10, p. 790',
    )),
    ('SIGN-18', (
        'GUIDANCE',
        'Portable supports max 3 days (exceptions)',
        'Sec. 6F.02 ¶11-12, p. 790-791',
    )),
    ('SIGN-19', (
        'GUIDANCE',
        'Barricade rail coverage; 7 ft for large signs STANDARD part',
        'Sec. 6F.02 ¶14-15, p. 791',
    )),
    ('SIGN-20', (
        'STANDARD',
        'Lane Closed signs W20-5/5a',
        'Sec. 6H.07 ¶01-02, p. 805',
    )),
    ('SIGN-21', (
        'GUIDANCE',
        'Flagger W20-7 advance',
        'Sec. 6H.15 ¶01-02; TA-10 note 8; TA-13 note 7, p. 806, 878, 884',
    )),
    ('SIGN-22', (
        'STANDARD',
        'ONE LANE ROAD W20-4 only for shared lane',
        'Sec. 6H.06 ¶01, p. 805',
    )),
    ('SIGN-23', (
        'GUIDANCE',
        'ROAD CLOSED W20-3; R11-2 on Type 3',
        'Sec. 6H.05 ¶01; Sec. 6G.04 ¶01-04, p. 793, 805',
    )),
    ('SIGN-24', (
        'STANDARD',
        'Shoulder Work legends; freeway sequence GUIDANCE part',
        'Sec. 6H.22 ¶02-04, p. 807',
    )),
    ('SIGN-25', (
        'GUIDANCE',
        'END ROAD WORK G20-2',
        'Sec. 6H.36 ¶01-02, p. 810',
    )),
    ('SIGN-26', (
        'GUIDANCE',
        'ROAD WORK NEXT XX MILES >2 mi; whole mile STANDARD',
        'Sec. 6H.35 ¶01-03, p. 810',
    )),
    ('SIGN-27', (
        'GUIDANCE',
        'Pedestrian SIDEWALK CLOSED R9 series',
        'Sec. 6G.10 ¶02-05, p. 797',
    )),
    ('SIGN-28', (
        'STANDARD',
        'Audible devices with SIDEWALK CLOSED CROSS HERE',
        'TA-28 note 5-6; TA-29 note 3-4, p. 914, 916',
    )),
    ('SIGN-29', (
        'STANDARD',
        'Crosswalk closure no parking 50 ft',
        'TA-29 note 2, p. 916',
    )),
    ('SIGN-30', (
        'STANDARD',
        'Advisory plaques only with warning signs',
        'Sec. 6H.32 ¶02; Sec. 6H.33 ¶03, p. 809-810',
    )),
    ('SIGN-31', (
        'STANDARD',
        'TTC warning sign sizes Table 6H-1',
        'Table 6H-1; Table 6G-1, p. 796, 803-804',
    )),
    ('SHLD-02', (
        'OPTION',
        'Short duration 60 min may eliminate signs if vehicle lights',
        'TA-3 note 5-7, p. 864',
    )),
    ('SHLD-03', (
        'OPTION',
        'TA-1 ROAD WORK AHEAD omit behind barrier/24in curb/15ft',
        'TA-1 note 3, p. 860',
    )),
    ('TAPER-01', (
        'GUIDANCE',
        'Taper length L formulas',
        'Table 6B-4; Sec. 6B.08 ¶04, p. 775',
    )),
    ('TAPER-02', (
        'GUIDANCE',
        'Taper type lengths merging L, shifting 0.5L, shoulder 0.33L, one-lane/downstream 50-100',
        'Table 6B-3; Sec. 6B.08 ¶08,10, p. 775-776',
    )),
    ('TAPER-03', (
        'GUIDANCE',
        'Downstream and one-lane taper device spacing ~20 ft',
        'Sec. 6B.08 ¶12,14, p. 776',
    )),
    ('TAPER-04', (
        'OPTION',
        'Taper length adjustment near ramps/curves',
        'Sec. 6B.08 ¶01,03, p. 775',
    )),
    ('TAPER-05', (
        'GUIDANCE',
        'Shoulder as travel lane uses merging/shifting taper',
        'Sec. 6B.08 ¶10, p. 776',
    )),
    ('TAPER-06', (
        'STANDARD',
        'Near-side intersection taper not both lanes',
        'TA-21 note 1, p. 900',
    )),
    ('BUFFER-01', (
        'OPTION',
        'Longitudinal buffer Table 6B-2 lengths',
        'Sec. 6B.06 ¶09,11; Table 6B-2, p. 773, 775',
    )),
    ('BUFFER-02', (
        'GUIDANCE',
        'No work/storage in buffer; lateral judgment',
        'Sec. 6B.06 ¶07,13,15, p. 773, 775',
    )),
    ('CHAN-01', (
        'GUIDANCE',
        'Device spacing taper 1S tangent 2S',
        'Sec. 6K.01 ¶04, p. 815',
    )),
    ('CHAN-02', (
        'GUIDANCE',
        'Extension 2S beyond transition',
        'Sec. 6K.01 ¶05, p. 815',
    )),
    ('CHAN-03', (
        'STANDARD',
        'Cone heights 18/28 in',
        'Sec. 6K.03 ¶01-03, p. 818',
    )),
    ('CHAN-04', (
        'STANDARD',
        'Tubular markers',
        'Sec. 6K.04 ¶01-04,07, p. 819',
    )),
    ('CHAN-05', (
        'STANDARD',
        'Vertical panels',
        'Sec. 6K.05 ¶01, p. 819',
    )),
    ('CHAN-06', (
        'STANDARD',
        'Drums',
        'Sec. 6K.06 ¶01, p. 820',
    )),
    ('CHAN-07', (
        'STANDARD',
        'Barricade rails',
        'Sec. 6K.07 ¶03-05, p. 820',
    )),
    ('CHAN-08', (
        'GUIDANCE',
        'Barricade type selection',
        'Sec. 6K.07 ¶17-19,21-22, p. 821',
    )),
    ('CHAN-09', (
        'GUIDANCE',
        'Direction Indicator Barricades',
        'Sec. 6K.08 ¶01-04, p. 821',
    )),
    ('CHAN-10', (
        'GUIDANCE',
        'Temporary barrier not for merging taper except low-speed urban',
        'Sec. 6K.09 ¶03-06, p. 822',
    )),
    ('CHAN-11', (
        'STANDARD',
        'Longitudinal channelizers / lane separators',
        'Sec. 6K.10 ¶08; Sec. 6K.11 ¶02,05-06, p. 822-823',
    )),
    ('CHAN-12', (
        'GUIDANCE',
        'Warning lights on devices',
        'Sec. 6L.07 ¶06,09-12,14, p. 835',
    )),
    ('PED-01', (
        'GUIDANCE',
        'Pedestrian path width 60 in; passing every 200 ft',
        'Sec. 6K.07 ¶10; TA-28 note 14, p. 820, 914',
    )),
    ('PED-02', (
        'STANDARD',
        'Sidewalk closure detectable devices',
        'Sec. 6K.02 ¶07-08, p. 817-818',
    )),
    ('PED-03', (
        'STANDARD',
        'Temporary ramps 12:1',
        'TA-28 note 2, p. 914',
    )),
    ('PED-04', (
        'GUIDANCE',
        'Direct pedestrians at intersections',
        'Sec. 6C.02 ¶09; TA-29 note 5, p. 778, 916',
    )),
    ('PED-05', (
        'GUIDANCE',
        'Close crosswalk if work across it',
        'TA-21 note 3, p. 900',
    )),
    ('SHLD-01', (
        'STANDARD',
        'Wide shoulder >=8 ft advance warning and channelization',
        'TA-3 note 8; TA-33 note 3, p. 864, 924',
    )),
    ('ARROW-01', (
        'GUIDANCE',
        'Arrow mode for lane closure multi-lane',
        'Sec. 6L.06 ¶02-03,17, p. 832-833',
    )),
    ('ARROW-02', (
        'STANDARD',
        'Arrow board per closed freeway lane',
        'TA-33 note 7; TA-37 note 1; Sec. 6L.06 ¶21, p. 834, 924, 932',
    )),
    ('ARROW-03', (
        'STANDARD',
        'Caution mode for shoulder/two-lane; no lane shift indication',
        'Sec. 6L.06 ¶18,25, p. 833, 835',
    )),
    ('ARROW-04', (
        'GUIDANCE',
        'Arrow board at beginning of merging taper',
        'Sec. 6L.06 ¶04,19-20; Fig. 6P-33, p. 833, 925',
    )),
    ('ARROW-05', (
        'GUIDANCE',
        'Multiple lane closure board placement',
        'Sec. 6L.06 ¶22; TA-37 note 2, p. 834, 932',
    )),
    ('ARROW-06', (
        'STANDARD',
        'Arrow board types A-D sizes',
        'Fig. 6L-3; Sec. 6L.06 ¶05-06, p. 833-834',
    )),
    ('ARROW-07', (
        'GUIDANCE',
        'Mounting height 7 ft; flash rate; vehicle lights',
        'Sec. 6L.06 ¶04,09,11-15,24, p. 833, 835',
    )),
    ('FLAG-01', (
        'STANDARD',
        'Flagger uses paddle/flag/AFAD; no hand alone',
        'Sec. 6D.05 ¶02; Sec. 6D.02 ¶01, p. 783, 785',
    )),
    ('FLAG-02', (
        'STANDARD',
        'Flagger station stopping distance; Table 6B-2 may be used',
        'Sec. 6D.06 ¶01-03, p. 786',
    )),
    ('FLAG-03', (
        'GUIDANCE',
        'Escape route; stand on shoulder; visible alone',
        'Sec. 6D.06 ¶04; Sec. 6D.05 ¶06, p. 786',
    )),
    ('FLAG-04', (
        'STANDARD',
        'Advance warning and night illumination',
        'Sec. 6D.06 ¶05, p. 786',
    )),
    ('FLAG-05', (
        'GUIDANCE',
        'One-lane two-way flagger each end / single option',
        'Sec. 6E.02 ¶01-03, p. 787',
    )),
    ('FLAG-06', (
        'GUIDANCE',
        'Flag transfer max ~1 mile',
        'Sec. 6E.03 ¶02, p. 787',
    )),
    ('FLAG-07', (
        'GUIDANCE',
        'TA-10 buffer before curve; sign order',
        'TA-10 note 6; Fig. 6P-10, p. 878-879',
    )),
    ('FLAG-08', (
        'STANDARD',
        'AFAD placement and attendance',
        'Sec. 6L.02 ¶04-06,09-15, p. 825-826',
    )),
    ('FLAG-09', (
        'STANDARD',
        'STOP/SLOW AFAD 6 ft / 24x24',
        'Sec. 6L.03 ¶02, p. 826',
    )),
    ('FLAG-10', (
        'STANDARD',
        'TA-13 flagger or LEO for short closure',
        'TA-13 note 1-2, p. 884',
    )),
)
