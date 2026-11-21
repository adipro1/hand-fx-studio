// Stylised filter library used by region effects (Filter Frame, Finger Bands, Glass Prism).
// Requires: common.glsl, uniform sampler2D u_src.
// Mode ids must match rendering/filter_modes.py

#define F_HALFTONE   0
#define F_PIXELATE   1
#define F_INVERT     2
#define F_THERMAL    3
#define F_RAINBOW    4
#define F_EDGES      5
#define F_SCANLINE   6
#define F_DOTS_DARK  7
#define F_BLUR       8
#define F_POSTER     9
#define F_GLASS      10
#define F_XRAY       11
#define F_LED        12
#define F_RGBSPLIT   13
#define F_MIRROR     14
#define F_NONE       15

vec3 src(vec2 uv) { return texture(u_src, clamp(uv, vec2(0.001), vec2(0.999))).rgb; }

vec3 src_soft(vec2 uv, float r) {
    vec2 t = r / u_res;
    return (src(uv) * 2.0 + src(uv + vec2(t.x, 0)) + src(uv - vec2(t.x, 0))
            + src(uv + vec2(0, t.y)) + src(uv - vec2(0, t.y))) / 6.0;
}

float sobel(vec2 uv, float spread) {
    vec2 t = spread / u_res;
    float tl = luma(src(uv + t * vec2(-1, -1))), tc = luma(src(uv + t * vec2(0, -1))), tr = luma(src(uv + t * vec2(1, -1)));
    float ml = luma(src(uv + t * vec2(-1, 0))), mr = luma(src(uv + t * vec2(1, 0)));
    float bl = luma(src(uv + t * vec2(-1, 1))), bc = luma(src(uv + t * vec2(0, 1))), br = luma(src(uv + t * vec2(1, 1)));
    float gx = -tl - 2.0 * ml - bl + tr + 2.0 * mr + br;
    float gy = -tl - 2.0 * tc - tr + bl + 2.0 * bc + br;
    return length(vec2(gx, gy));
}

vec3 halftone(vec2 uv, vec3 bg, vec3 ink, float cell, float angle) {
    vec2 px = uv * u_res;
    vec2 r = rot2(angle) * px;
    vec2 cc = (floor(r / cell) + 0.5) * cell;
    vec2 back = rot2(-angle) * cc;
    float l = luma(src_soft(back / u_res, cell * 0.3));
    l = smoothstep(0.12, 0.92, l);
    l = l * l * (3.0 - 2.0 * l);
    float rad = sqrt(l) * cell * 0.66;
    float d = length(r - cc);
    float m = 1.0 - smoothstep(rad - 0.7, rad + 0.7, d);
    return mix(bg, ink, m);
}

vec3 apply_filter(int mode, vec2 uv, float amount, float cell, vec3 c1, vec3 c2) {
    vec2 px = uv * u_res;
    if (mode == F_HALFTONE) {
        return halftone(uv, c1, c2, cell, 0.785);
    } else if (mode == F_PIXELATE) {
        float b = cell * 2.2;
        vec2 q = (floor(px / b) + 0.5) * b / u_res;
        vec3 c = src_soft(q, b * 0.35);
        return floor(c * 12.0 + 0.5) / 12.0;
    } else if (mode == F_INVERT) {
        vec3 c = 1.0 - src(uv);
        return mix(c, c * c1 * 1.6, 0.35 * amount);
    } else if (mode == F_THERMAL) {
        float l = luma(src_soft(uv, 3.0));
        l = smoothstep(0.03, 0.85, l);
        return jet(l * (0.85 + 0.25 * amount));
    } else if (mode == F_RAINBOW) {
        float l = luma(src_soft(uv, 2.0));
        return turbo(fract(l * (0.9 + amount * 0.4) + 0.08 * sin(u_time * 0.7)) * 0.92 + 0.04);
    } else if (mode == F_EDGES) {
        float e = sobel(uv, 1.3);
        e = smoothstep(0.10, 0.45, e * (0.7 + amount));
        return mix(vec3(0.0), c1, e);
    } else if (mode == F_SCANLINE) {
        float row = floor(px.y / 3.0);
        float tq = floor(u_time * 14.0);
        float g = step(0.82, hash12(vec2(floor(row / 6.0), tq))) * (hash12(vec2(row, tq)) - 0.5) * 0.06;
        vec3 c = src(uv + vec2(g, 0.0));
        float l = luma(c);
        float stripe = step(0.4, fract(px.y / 4.0));
        float n = hash12(floor(px / vec2(3.0, 1.0)) + tq);
        float v = clamp(pow(l, 0.8) * 2.4 * stripe * (0.5 + 0.9 * n), 0.0, 1.0);
        return mix(c1, c2, v);
    } else if (mode == F_DOTS_DARK) {
        return halftone(uv, vec3(0.0), c2, cell * 0.8, 0.3);
    } else if (mode == F_BLUR) {
        vec3 acc = vec3(0.0);
        float rad = cell * 2.0;
        for (int i = 0; i < 24; i++) {
            float fi = float(i);
            float r = sqrt((fi + 0.5) / 24.0) * rad;
            float a = fi * 2.39996;
            acc += src(uv + vec2(cos(a), sin(a)) * r / u_res);
        }
        return acc / 24.0;
    } else if (mode == F_POSTER) {
        vec3 c = sat_adjust(src_soft(uv, 1.5), 1.8);
        c = hue_shift(c, u_time * 0.05);
        return floor(c * 3.0 + 0.5) / 3.0;
    } else if (mode == F_GLASS) {
        vec3 c = src(uv);
        float l = luma(c);
        c = mix(vec3(l), c, 0.3);
        c = pow(clamp(c * 1.4, 0.0, 1.0), vec3(0.9));
        return c * mix(vec3(1.0), c1, 0.55);
    } else if (mode == F_XRAY) {
        float l = 1.0 - luma(src_soft(uv, 1.5));
        float e = smoothstep(0.1, 0.5, sobel(uv, 1.5));
        return c1 * pow(l, 1.6) * 1.3 + vec3(e) * 0.6;
    } else if (mode == F_LED) {
        float b = cell * 1.3;
        vec2 cc = (floor(px / b) + 0.5) * b;
        vec3 c = src(cc / u_res);
        c = floor(sat_adjust(c, 1.4) * 4.0 + 0.5) / 4.0;
        float d = length(px - cc) / b;
        return c * (1.0 - smoothstep(0.32, 0.42, d)) * 1.3;
    } else if (mode == F_RGBSPLIT) {
        float tq = floor(u_time * 10.0);
        float o = (0.006 + 0.01 * amount) * (0.6 + hash12(vec2(tq, 1.0)));
        float row = floor(px.y / 18.0);
        float g = step(0.75, hash12(vec2(row, tq))) * (hash12(vec2(tq, row)) - 0.5) * 0.08;
        vec2 u2 = uv + vec2(g, 0.0);
        return vec3(src(u2 + vec2(o, 0)).r, src(u2).g, src(u2 - vec2(o, 0)).b);
    } else if (mode == F_MIRROR) {
        return src(vec2(1.0 - uv.x, uv.y));
    }
    return src(uv);
}
