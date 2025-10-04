from typing import Set, List, Tuple, Optional
from osgeo import ogr, osr
import math

ID_FIELD_NAME: str = "qa_assistant_id"
MIN_AREA_HA_FOR_POLYGON: float = 4.0
METERS_SQ_PER_HECTARE: float = 10000.0
SIMPLIFY_TOLERANCE: float = 0.0001
OPTIONAL_FIELDS: List[str] = ['ProductionPlace', 'ProducerName', 'ProducerCountry', 'Area']
DATASET_TRIGGERS: Set[str] = {".shp", ".geojson"}
VALID_ISO2_CODES: Set[str] = {
    'AD', 'AE', 'AF', 'AG', 'AI', 'AL', 'AM', 'AO', 'AQ', 'AR', 'AS', 'AT', 'AU', 'AW', 'AX', 'AZ', 'BA', 'BB',
    'BD', 'BE', 'BF', 'BG', 'BH', 'BI', 'BJ', 'BL', 'BM', 'BN', 'BO', 'BQ', 'BR', 'BS', 'BT', 'BV', 'BW', 'BY',
    'BZ', 'CA', 'CC', 'CD', 'CF', 'CG', 'CH', 'CI', 'CK', 'CL', 'CM', 'CN', 'CO', 'CR', 'CU', 'CV', 'CW', 'CX',
    'CY', 'CZ', 'DE', 'DJ', 'DK', 'DM', 'DO', 'DZ', 'EC', 'EE', 'EG', 'EH', 'ER', 'ES', 'ET', 'FI', 'FJ', 'FK',
    'FM', 'FO', 'FR', 'GA', 'GB', 'GD', 'GE', 'GF', 'GG', 'GH', 'GI', 'GL', 'GM', 'GN', 'GP', 'GQ', 'GR', 'GS',
    'GT', 'GU', 'GW', 'GY', 'HK', 'HM', 'HN', 'HR', 'HT', 'HU', 'ID', 'IE', 'IL', 'IM', 'IN', 'IO', 'IQ', 'IR',
    'IS', 'IT', 'JE', 'JM', 'JO', 'JP', 'KE', 'KG', 'KH', 'KI', 'KM', 'KN', 'KP', 'KR', 'KW', 'KY', 'KZ', 'LA',
    'LB', 'LC', 'LI', 'LK', 'LS', 'LT', 'LU', 'LV', 'LY', 'MA', 'MC', 'MD', 'ME', 'MF', 'MG', 'MH', 'MK',
    'ML', 'MM', 'MN', 'MO', 'MP', 'MQ', 'MR', 'MS', 'MT', 'MU', 'MV', 'MW', 'MX', 'MY', 'MZ', 'NA', 'NC', 'NE',
    'NF', 'NG', 'NI', 'NL', 'NO', 'NP', 'NR', 'NU', 'NZ', 'OM', 'PA', 'PE', 'PF', 'PG', 'PH', 'PK', 'PL', 'PM',
    'PN', 'PR', 'PS', 'PT', 'PW', 'PY', 'QA', 'RE', 'RO', 'RS', 'RU', 'RW', 'SA', 'SB', 'SC', 'SD', 'SE', 'SG',
    'SH', 'SI', 'SJ', 'SK', 'SL', 'SM', 'SN', 'SO', 'SR', 'SS', 'ST', 'SV', 'SX', 'SY', 'SZ', 'TC', 'TD', 'TF',
    'TG', 'TH', 'TJ', 'TK', 'TL', 'TM', 'TN', 'TO', 'TR', 'TT', 'TV', 'TW', 'TZ', 'UA', 'UG', 'UM', 'US', 'UY',
    'UZ', 'VA', 'VC', 'VE', 'VG', 'VI', 'VN', 'VU', 'WF', 'WS', 'YE', 'YT', 'ZA', 'ZM', 'ZW'
}

def validate_global_crs(ds: ogr.DataSource) -> bool:
    """
    Checks if a dataset's CRS is equivalent to WGS84 (EPSG:4326).
    Args:
        ds: The opened OGR DataSource object.
    Returns:
        True if the CRS is WGS84, False otherwise.
    """
    wgs84_srs = osr.SpatialReference()
    wgs84_srs.ImportFromEPSG(4326)
    wgs84_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    
    try:
        layer = ds.GetLayer()
        if layer is None:
            return False
        srs = layer.GetSpatialRef()
        if srs is None:
            return False
        
        return srs.IsSame(wgs84_srs)
        
    except Exception:
        return False

def get_all_points(geom: ogr.Geometry) -> List[Tuple[float, float]]:
    """Recursively extracts all vertex coordinates from a geometry object."""
    points = []
    geom_type = geom.GetGeometryType() & 0x000000ff
    if geom_type in (ogr.wkbPoint, ogr.wkbMultiPoint, ogr.wkbLineString, ogr.wkbMultiLineString):
        for i in range(geom.GetPointCount()): points.append(geom.GetPoint_2D(i))
    elif geom_type in (ogr.wkbPolygon, ogr.wkbMultiPolygon):
        for i in range(geom.GetGeometryCount()):
            sub_geom = geom.GetGeometryRef(i)
            if sub_geom: points.extend(get_all_points(sub_geom))
    return points

def validate_geometry_vertices(geom: ogr.Geometry) -> Tuple[bool, str]:
    """Validates that all geometry vertices are within valid geographic bounds."""
    if not geom or geom.IsEmpty(): return True, ""
    for lon, lat in get_all_points(geom):
        if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
            return False, f"Invalid coordinate range: [{lon:.5f}, {lat:.5f}]"
    return True, ""

def check_optional_properties(feature: ogr.Feature) -> str:
    """Checks the status of optional EUDR-related attributes."""
    notes = []
    for field_name in OPTIONAL_FIELDS:
        field_index = feature.GetFieldIndex(field_name)
        if field_index == -1: notes.append("Not included"); continue
        value = feature.GetField(field_index)
        if field_name == 'ProducerCountry':
            if isinstance(value, str) and value.upper() in VALID_ISO2_CODES: notes.append("OK")
            else: notes.append(f"Invalid value: '{value}'")
        elif field_name == 'Area':
            if isinstance(value, (int, float)): notes.append("OK")
            else: notes.append("Invalid data type")
        else: notes.append("OK")
    return "; ".join(notes)

def summarize_attribute_status(all_notes: List[str]) -> str:
    """Provides a high-level summary of attribute validation results."""
    if not all_notes: return "N/A"
    has_issues = any("Invalid" in note for note in all_notes)
    all_ok = all(note == "OK; OK; OK; OK" for note in all_notes)
    if all_ok: return "All optional attributes valid"
    if has_issues: return "Attribute issues found"
    return "Some attributes not included"
