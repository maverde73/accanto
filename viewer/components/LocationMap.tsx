"use client";

import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import { relative } from "@/lib/time";
import type { LocationPoint } from "@/lib/types";

/** Live map.
 *
 * Two honesty rules are enforced visually:
 *
 *  - the accuracy circle is always drawn. Indoors a fix drifts by tens of
 *    metres, and a confident dot in the wrong place is its own kind of lie;
 *  - a coarse fix is labelled as such, so nobody reads a rounded position as an
 *    address.
 */

const OSM_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap",
    },
  },
  layers: [{ id: "osm", type: "raster", source: "osm" }],
};

export function LocationMap({
  subjectId,
  initial,
}: {
  subjectId: string;
  initial: LocationPoint | null;
}) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const marker = useRef<maplibregl.Marker | null>(null);
  const [point, setPoint] = useState(initial);
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    if (!container.current || map.current) return;

    map.current = new maplibregl.Map({
      container: container.current,
      style: OSM_STYLE,
      center: point ? [point.lon, point.lat] : [12.5, 42.5],
      zoom: point ? 15 : 5,
      attributionControl: { compact: true },
    });

    return () => {
      map.current?.remove();
      map.current = null;
    };
  }, []);

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 20_000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    const source = new EventSource(`/api/stream?subject=${encodeURIComponent(subjectId)}`);
    source.addEventListener("location", (event) => {
      const data = JSON.parse((event as MessageEvent<string>).data) as LocationPoint;
      setPoint(data);
      setNow(new Date());
    });
    return () => source.close();
  }, [subjectId]);

  useEffect(() => {
    if (!map.current || !point) return;

    if (!marker.current) {
      const element = document.createElement("div");
      element.style.cssText =
        "width:16px;height:16px;border-radius:50%;background:#4A6B5C;border:3px solid #fff;box-shadow:0 1px 6px rgba(0,0,0,.3)";
      marker.current = new maplibregl.Marker({ element });
    }
    marker.current.setLngLat([point.lon, point.lat]).addTo(map.current);
    map.current.easeTo({ center: [point.lon, point.lat], duration: 600 });

    drawAccuracy(map.current, point);
  }, [point]);

  if (!point) {
    return (
      <div className="banner tone-grey">
        Nessuna posizione disponibile. Non è un allarme: probabilmente il collegamento è
        interrotto o il telefono è spento.
      </div>
    );
  }

  return (
    <>
      <div ref={container} className="map-canvas" />
      <div className="card" style={{ padding: 14 }}>
        <div style={{ fontSize: 14, fontWeight: 600 }}>
          {point.precision === "coarse" ? "Zona approssimativa" : "Posizione"}
        </div>
        <div className="row-meta" style={{ marginTop: 2 }}>
          {relative(point.at, now)}
          {point.accuracy_m ? ` · precisione ±${Math.round(point.accuracy_m)} m` : ""}
        </div>
        {point.precision === "coarse" ? (
          <div className="row-note" style={{ marginTop: 6 }}>
            I tuoi permessi mostrano solo la zona, non l'indirizzo esatto.
          </div>
        ) : null}
      </div>
    </>
  );
}

function drawAccuracy(map: maplibregl.Map, point: LocationPoint): void {
  const radius = point.accuracy_m ?? 0;
  if (radius <= 0) return;

  const data = circlePolygon(point.lat, point.lon, radius);
  const existing = map.getSource("accuracy") as maplibregl.GeoJSONSource | undefined;

  if (existing) {
    existing.setData(data);
    return;
  }

  const add = () => {
    if (map.getSource("accuracy")) return;
    map.addSource("accuracy", { type: "geojson", data });
    map.addLayer({
      id: "accuracy-fill",
      type: "fill",
      source: "accuracy",
      paint: { "fill-color": "#4A6B5C", "fill-opacity": 0.14 },
    });
  };

  if (map.isStyleLoaded()) add();
  else map.once("load", add);
}

function circlePolygon(lat: number, lon: number, radiusM: number): GeoJSON.Feature {
  const points = 48;
  const latRadius = radiusM / 111_320;
  const lonRadius = latRadius / Math.cos((lat * Math.PI) / 180);
  const ring: [number, number][] = [];

  for (let i = 0; i <= points; i += 1) {
    const angle = (i / points) * 2 * Math.PI;
    ring.push([lon + lonRadius * Math.cos(angle), lat + latRadius * Math.sin(angle)]);
  }

  return {
    type: "Feature",
    properties: {},
    geometry: { type: "Polygon", coordinates: [ring] },
  };
}
