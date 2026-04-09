'use client';

import { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { useTheme } from './ThemeProvider';
import {
  buildGoogleMapsUrl,
  escapeHtml,
  formatDateTime,
  getRecordActivityLabel,
  getCoordinateLabel,
  formatLocation,
  formatSourceLabel,
  getCountryDisplayName,
  hasCountryValue,
  hasLocationValue,
} from '@/lib/event-utils';

interface MapEvent {
  id?: string;
  lat: number;
  lng: number;
  title: string;
  severity: number;
  type: string;
  country?: string;
  region?: string;
  city?: string;
  source?: string;
  sourceUrl?: string;
  sourceDomain?: string;
  sourceStatus?: string;
  sourceStatusReason?: string;
  detailHref?: string;
  detailAvailable?: boolean;
  publishedAt?: string;
  eventDate?: string;
  createdAt?: string;
  ingestedAt?: string;
  updatedAt?: string;
}

function severityColor(severity: number): string {
  if (severity >= 8) return '#f43f5e';
  if (severity >= 6) return '#f59e0b';
  if (severity >= 4) return '#6366f1';
  return '#10b981';
}

export default function MapView({ events = [] }: { events: MapEvent[] }) {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);
  const tileLayerRef = useRef<L.TileLayer | null>(null);
  const { theme } = useTheme();

  useEffect(() => {
    if (!mapRef.current || mapInstanceRef.current) return;

    const map = L.map(mapRef.current, {
      center: [20, 30],
      zoom: 2.5,
      zoomControl: false,
      attributionControl: false,
    });

    const initialUrl = theme === 'dark'
      ? 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager_labels_under/{z}/{x}/{y}{r}.png'
      : 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png';

    const tileLayer = L.tileLayer(initialUrl, {
      maxZoom: 18,
      className: theme === 'dark' ? 'map-tiles-dark' : '',
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
    }).addTo(map);

    tileLayerRef.current = tileLayer;
    L.control.zoom({ position: 'bottomright' }).addTo(map);
    mapInstanceRef.current = map;

    return () => {
      map.remove();
      mapInstanceRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!tileLayerRef.current) return;
    const newUrl = theme === 'dark'
      ? 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png'
      : 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png';
    tileLayerRef.current.setUrl(newUrl);
  }, [theme]);

  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;

    // Clear existing markers
    map.eachLayer((layer) => {
      if (layer instanceof L.CircleMarker) {
        map.removeLayer(layer);
      }
    });

    const markerPoints: Array<[number, number]> = [];

    // Add event markers
    events.forEach((event) => {
      markerPoints.push([event.lat, event.lng]);
      const color = severityColor(event.severity);
      const circle = L.circleMarker([event.lat, event.lng], {
        radius: Math.max(4, event.severity * 1.2),
        fillColor: color,
        color: color,
        weight: 1,
        opacity: 0.9,
        fillOpacity: 0.6,
      });

      const textColor = theme === 'dark' ? '#f9fafb' : '#111827';
      const bgStyle = theme === 'dark' ? '' : 'background: #fff; padding: 4px; border-radius: 4px;';
      const title = escapeHtml(event.title);
      const location = escapeHtml(formatLocation(event));
      const country = escapeHtml(getCountryDisplayName(event.country));
      const type = escapeHtml(formatSourceLabel(event.type));
      const source = escapeHtml(formatSourceLabel(event.source));
      const detailHref = event.detailHref || '/dashboard/events';
      const sourceHref = event.sourceUrl ? escapeHtml(event.sourceUrl) : '';
      const googleMapsHref = buildGoogleMapsUrl(event);
      const coordinateLabel = escapeHtml(getCoordinateLabel({ latitude: event.lat, longitude: event.lng }));
      const sourceTimeLabel = event.publishedAt ? escapeHtml(formatDateTime(event.publishedAt)) : 'Not supplied by source';
      const eventDateLabel = event.eventDate ? escapeHtml(formatDateTime(event.eventDate)) : 'Not available';
      const recordActivityLabel = escapeHtml(
        getRecordActivityLabel({
          created_at: event.createdAt,
          ingested_at: event.ingestedAt,
          updated_at: event.updatedAt,
        })
      );
      const locationRows = [
        hasLocationValue({ city: event.city, region: event.region, country: event.country, raw_data: undefined })
          ? `<div><span style="color:#9ca3af;">Location:</span> ${location}</div>`
          : '',
        hasCountryValue({ country: event.country, raw_data: undefined })
          ? `<div><span style="color:#9ca3af;">Country:</span> ${country}</div>`
          : '',
        `<div><span style="color:#9ca3af;">Coordinates:</span> ${coordinateLabel}</div>`,
      ].filter(Boolean).join('');
      
      // We manually build popup HTML so we adapt font color based on theme
      circle.bindPopup(`
        <div style="font-family:Inter,sans-serif; font-size:13px; max-width:280px; color:${textColor}; ${bgStyle}">
          <div style="font-size:10px; font-weight:700; letter-spacing:0.08em; text-transform:uppercase; color:#9ca3af; margin-bottom:6px;">
            ${source}
          </div>
          <div style="color:var(--accent-indigo); font-size:14px; font-weight:800; line-height:1.45; margin-bottom:8px; word-break:break-word;">
            ${title}
          </div>
          <div style="display:inline-flex; margin-bottom:8px; padding:4px 8px; border-radius:999px; background:rgba(16,185,129,0.16); color:#10b981; font-size:11px; font-weight:800;">
            Official source
          </div>
          <div style="display:flex; flex-direction:column; gap:4px; line-height:1.45; margin-bottom:10px;">
            ${locationRows}
            <div><span style="color:#9ca3af;">Type:</span> ${type}</div>
            <div><span style="color:#9ca3af;">Severity:</span> ${event.severity}/10</div>
            <div><span style="color:#9ca3af;">Source time:</span> ${sourceTimeLabel}</div>
            <div><span style="color:#9ca3af;">Event date:</span> ${eventDateLabel}</div>
            <div><span style="color:#9ca3af;">Record activity:</span> ${recordActivityLabel}</div>
          </div>
          <div style="display:flex; flex-wrap:wrap; gap:6px;">
            ${event.detailAvailable ? `
              <a href="${detailHref}" style="padding:5px 8px; border-radius:8px; background:rgba(99,102,241,0.16); color:${textColor}; text-decoration:none; font-weight:700; font-size:11px;">
                View details
              </a>
            ` : `
              <span style="padding:5px 8px; border-radius:8px; background:rgba(245,158,11,0.16); color:${textColor}; text-decoration:none; font-weight:700; font-size:11px;">
                Summary only
              </span>
            `}
            ${googleMapsHref ? `
              <a href="${googleMapsHref}" target="_blank" rel="noopener noreferrer" style="padding:5px 8px; border-radius:8px; background:rgba(16,185,129,0.16); color:${textColor}; text-decoration:none; font-weight:700; font-size:11px;">
                Google Maps
              </a>
            ` : ''}
            ${sourceHref ? `
              <a href="${sourceHref}" target="_blank" rel="noopener noreferrer" style="padding:5px 8px; border-radius:8px; background:rgba(6,182,212,0.16); color:${textColor}; text-decoration:none; font-weight:700; font-size:11px;">
                Open source
              </a>
            ` : ''}
          </div>
        </div>
      `);

      circle.addTo(map);
    });

    if (markerPoints.length === 1) {
      map.setView(markerPoints[0], 7);
      return;
    }

    if (markerPoints.length > 1) {
      map.fitBounds(markerPoints, { padding: [24, 24] });
      return;
    }

    map.setView([20, 30], 2.5);
  }, [events, theme]);

  return <div ref={mapRef} style={{ width: '100%', height: '100%' }} />;
}
