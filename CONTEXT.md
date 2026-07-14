# Weather Forecast Normalization

This context defines the weather measurements normalized across forecast
providers so that physically different quantities are not conflated.

## Language

**Liquid-equivalent precipitation**:
The total depth of liquid water represented by all precipitation during a
forecast interval, regardless of whether it falls as rain, snow, or another
form.
_Avoid_: Rain, rain amount

**Rain amount**:
The depth of liquid precipitation specifically attributable to rain during a
forecast interval.
_Avoid_: Precipitation, liquid-equivalent precipitation

**Liquid-equivalent snowfall**:
The depth of liquid water represented by snow falling during a forecast interval.
_Avoid_: Snowfall depth, snow depth

**New-snow depth**:
The physical depth of snow accumulating during a forecast interval.
_Avoid_: Snow depth

**Snowpack depth**:
The total physical depth of snow lying on the ground at a point in time.
_Avoid_: Snowfall depth, new-snow depth

**Forecast instant**:
An absolute point in time at which forecast conditions or an astronomical event
are valid.
_Avoid_: Local time, forecast date

**Forecast date**:
The civil calendar date at the forecast location for which daily conditions are
valid.
_Avoid_: UTC date, forecast instant

**Location time zone**:
The regional rules that determine the forecast location's UTC offset at each
instant, including daylight-saving transitions.
_Avoid_: UTC offset, fixed offset
