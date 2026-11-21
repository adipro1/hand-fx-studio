// Shared GLSL helpers. Included in every fragment shader via //#include common
// Coordinate convention: uv in [0,1], y points DOWN (image space).

uniform vec2 u_res;      // render target size in pixels
uniform float u_time;
uniform float u_aspect;  // width / height

const float PI = 3.14159265359;
const float TAU = 6.28318530718;

float luma(vec3 c) { return dot(c, vec3(0.299, 0.587, 0.114)); }

vec3 rgb2hsv(vec3 c) {
    vec4 K = vec4(0.0, -1.0 / 3.0, 2.0 / 3.0, -1.0);
    vec4 p = mix(vec4(c.bg, K.wz), vec4(c.gb, K.xy), step(c.b, c.g));
    vec4 q = mix(vec4(p.xyw, c.r), vec4(c.r, p.yzx), step(p.x, c.r));
    float d = q.x - min(q.w, q.y);
    float e = 1.0e-10;
    return vec3(abs(q.z + (q.w - q.y) / (6.0 * d + e)), d / (q.x + e), q.x);
}

vec3 hsv2rgb(vec3 c) {
    vec3 p = abs(fract(c.xxx + vec3(0.0, 2.0 / 3.0, 1.0 / 3.0)) * 6.0 - 3.0);
    return c.z * mix(vec3(1.0), clamp(p - 1.0, 0.0, 1.0), c.y);
}

vec3 hue_shift(vec3 c, float h) {
    vec3 hsv = rgb2hsv(c);
    hsv.x = fract(hsv.x + h);
    return hsv2rgb(hsv);
}

// Google "Turbo" colormap (polynomial approximation)
vec3 turbo(float x) {
    x = clamp(x, 0.0, 1.0);
    const vec4 kr4 = vec4(0.13572138, 4.61539260, -42.66032258, 132.13108234);
    const vec4 kg4 = vec4(0.09140261, 2.19418839, 4.84296658, -14.18503333);
    const vec4 kb4 = vec4(0.10667330, 12.64194608, -60.58204836, 110.36276771);
    const vec2 kr2 = vec2(-152.94239396, 59.28637943);
    const vec2 kg2 = vec2(4.27729857, 2.82956604);
    const vec2 kb2 = vec2(-89.90310912, 27.34824973);
    vec4 v4 = vec4(1.0, x, x * x, x * x * x);
    vec2 v2 = v4.zw * v4.z;
    return vec3(dot(v4, kr4) + dot(v2, kr2), dot(v4, kg4) + dot(v2, kg2), dot(v4, kb4) + dot(v2, kb2));
}

// Classic "jet" thermal colormap
vec3 jet(float x) {
    x = clamp(x, 0.0, 1.0);
    return clamp(vec3(1.5 - abs(4.0 * x - 3.0), 1.5 - abs(4.0 * x - 2.0), 1.5 - abs(4.0 * x - 1.0)), 0.0, 1.0);
}

float hash12(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}

float vnoise(vec2 p) {
    vec2 i = floor(p), f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash12(i), hash12(i + vec2(1, 0)), u.x),
               mix(hash12(i + vec2(0, 1)), hash12(i + vec2(1, 1)), u.x), u.y);
}

float fbm(vec2 p) {
    float v = 0.0, a = 0.5;
    for (int i = 0; i < 4; i++) { v += a * vnoise(p); p *= 2.03; a *= 0.5; }
    return v;
}

mat2 rot2(float a) { float c = cos(a), s = sin(a); return mat2(c, -s, s, c); }

// Aspect-corrected space: x scaled by aspect so distances are isotropic
vec2 to_asp(vec2 uv) { return vec2(uv.x * u_aspect, uv.y); }

float cross2(vec2 a, vec2 b) { return a.x * b.y - a.y * b.x; }

// Signed distance (aspect space) to a polygon given in uv; negative inside.
// Works for any simple polygon (even-odd rule).
float sd_poly(vec2 p, vec2 v[8], int n) {
    vec2 P = to_asp(p);
    vec2 V0 = to_asp(v[0]);
    float d = dot(P - V0, P - V0);
    float s = 1.0;
    for (int i = 0, j = n - 1; i < 8; j = i, i++) {
        if (i >= n) break;
        vec2 vi = to_asp(v[i]);
        vec2 vj = to_asp(v[j]);
        vec2 e = vj - vi;
        vec2 w = P - vi;
        vec2 b = w - e * clamp(dot(w, e) / max(dot(e, e), 1e-12), 0.0, 1.0);
        d = min(d, dot(b, b));
        bvec3 c = bvec3(P.y >= vi.y, P.y < vj.y, e.x * w.y > e.y * w.x);
        if (all(c) || all(not(c))) s *= -1.0;
    }
    return s * sqrt(d);
}

vec3 sat_adjust(vec3 c, float s) { float l = luma(c); return mix(vec3(l), c, s); }
