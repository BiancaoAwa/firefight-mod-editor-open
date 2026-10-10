/**
 * Test doubles: a `spawn` implementation that never starts a process, and the
 * canned CLI payloads used by the renderer tests.
 */
import { EventEmitter } from 'node:events';

/**
 * Build a fake `spawn`.
 * @param respond - `(argv, command, options) => spec`, where spec may hold
 *   `{ stdout, stderr, code, error, hold }`; `hold` keeps the child open so a
 *   timeout or an abort can be observed.
 */
export function makeFakeSpawn(respond = () => ({})) {
    const calls = [];
    const spawnImpl = (command, argv, options) => {
        const spec = respond(argv, command, options) ?? {};
        const child = new EventEmitter();
        child.stdout = new EventEmitter();
        child.stderr = new EventEmitter();
        child.killed = false;
        child.kill = () => {
            child.killed = true;
            setImmediate(() => child.emit('close', null));
        };
        calls.push({ command, argv, options, child });
        setImmediate(() => {
            if (spec.error !== undefined) {
                child.emit('error', spec.error);
                return;
            }
            if (spec.stdout)
                child.stdout.emit('data', spec.stdout);
            if (spec.stderr)
                child.stderr.emit('data', spec.stderr);
            if (spec.hold === true)
                return;
            child.emit('close', spec.code ?? 0);
        });
        return child;
    };
    return { spawnImpl, calls };
}

/** Canonical payloads shaped like the real CLI output. */
export const PAYLOADS = {
    list: {
        scope: 'Firefight',
        root: 'D:/games/Firefight',
        count: 2,
        entities: [
            { path: 'Data/Weapons/WEAPON_PISTOL_P38.txt', category: 'weapon', format: 'txt', bytes: 605 },
            { path: 'Data/Weapons/WEAPON_RIFLE_AK_103.txt', category: 'weapon', format: 'txt', bytes: 1180 },
        ],
    },
    show: { path: 'Data/Weapons/WEAPON_PISTOL_P38.txt', format: 'txt', toml: '[[weapon]]\nname = "P38"', warnings: [] },
    get: {
        path: 'Data/Weapons/WEAPON_PISTOL_P38.txt',
        field: 'weapon/name',
        count: 1,
        values: [{ path: 'weapon/name', line: 4, value: 'P38' }],
    },
    find: {
        query: { tag: 'flavour', value: 'FLAVOUR_BALL', path: null, ignore_case: false },
        count: 1,
        truncated: false,
        matches: [{ path: 'Data/Weapons/WEAPON_PISTOL_P38.txt', line: 9, tag: 'flavour', document_path: 'weapon/ammo/flavour', value: 'FLAVOUR_BALL' }],
    },
    stats: {
        scope: 'Firefight',
        root: 'D:/games/Firefight',
        files: 1840,
        bytes: 4003531,
        lists: 48,
        by_category: { weapon: 716, vehicle: 200 },
        by_format: { txt: 1800, xml: 40 },
        by_root: { weapon: 716 },
        errors: [],
    },
    refs: {
        scope: 'Firefight',
        count: 2,
        by_kind: { weapon: 2 },
        references: [
            { source: 'Data/Weapons/WEAPON_PISTOL_P38.txt', kind: 'sound', value: 'SFX_PISTOL', document_path: 'weapon/sound_shoot' },
            { source: 'Data/Weapons/WEAPON_PISTOL_P38.txt', kind: 'ammo', value: 'AMMO_9MM', document_path: 'weapon/ammo/type' },
        ],
        errors: [],
    },
    deps: {
        scope: 'Firefight',
        value: 'WEAPON_PISTOL_P38',
        count: 1,
        references: [{ source: 'Data/Vehicles/Chinese-CSK-181.txt', kind: 'weapon', document_path: 'squad/man/weapon/type' }],
        resolved: ['Data/Weapons/WEAPON_PISTOL_P38.txt'],
        unresolved: false,
        errors: [],
    },
    check: {
        scope: 'Firefight',
        files: 716,
        loaded: 716,
        skipped: 0,
        errors: [],
        warnings_total: 13,
        warning_files: 13,
        warning_samples: ['Data/Weapons/WEAPON_CANNON_25_M242.txt: utf-8 fallback'],
        dangling: ['SFX_MISSING'],
        ok: true,
    },
    export: {
        scope: 'Mod',
        to: 'D:/out',
        count: 1,
        files: [{ path: 'Data/Weapons/WEAPON_PISTOL_P38.txt', out: 'D:/out/Data/Weapons/WEAPON_PISTOL_P38.txt', bytes: 605, warnings: [] }],
        errors: [],
    },
};
