// The character, drawn front-facing. Origin = point on the floor between the feet.
// guy({pose: 'stand'|'sit', arms: 'phone'|'down'|'thumb'|'chin'|'relax', mood: 'neutral'|'happy'|'worried'|'think', flash: bool, blink: bool})
const C = {
  skin: '#f3c8a4', skinShade: '#e6b28c', hair: '#3a2a20', hoodie: '#e8492b', hoodieDark: '#c63b20',
  hoodieLight: '#f06447', jeans: '#36557d', jeansDark: '#2b4565', shoe: '#f7f5f0', sole: '#e8492b', ink: '#23252b',
};

function guy(o) {
  const sit = o.pose === 'sit';
  const dy = sit ? 70 : 0;            // the upper body sits lower
  const s = [];

  // legs
  if (sit) {
    s.push(`<rect x="-46" y="-118" width="40" height="44" rx="18" fill="${C.jeans}"/>`);
    s.push(`<rect x="6" y="-118" width="40" height="44" rx="18" fill="${C.jeans}"/>`);
    s.push(`<rect x="-42" y="-96" width="30" height="80" rx="13" fill="${C.jeansDark}"/>`);
    s.push(`<rect x="12" y="-96" width="30" height="80" rx="13" fill="${C.jeansDark}"/>`);
  } else {
    s.push(`<rect x="-40" y="-175" width="32" height="160" rx="14" fill="${C.jeans}"/>`);
    s.push(`<rect x="8" y="-175" width="32" height="160" rx="14" fill="${C.jeans}"/>`);
    s.push(`<path d="M-8 -170 L-4 -110" stroke="${C.jeansDark}" stroke-width="3"/>`);
  }
  // sneakers
  for (const x of [-27, 27]) {
    s.push(`<rect x="${x - 25}" y="-22" width="52" height="20" rx="10" fill="${C.shoe}" stroke="#cfc6b6" stroke-width="2"/>`);
    s.push(`<rect x="${x - 26}" y="-6" width="54" height="7" rx="3.5" fill="${C.sole}"/>`);
    s.push(`<path d="M${x - 8} -18 L${x + 8} -18" stroke="#cfc6b6" stroke-width="2"/>`);
  }

  s.push(`<g transform="translate(0 ${dy})">`);
  // hood behind the neck
  s.push(`<ellipse cx="0" cy="-282" rx="46" ry="18" fill="${C.hoodieDark}"/>`);
  // torso
  s.push(`<path d="M-64 -270 Q0 -296 64 -270 Q74 -220 72 -168 Q0 -150 -72 -168 Q-74 -220 -64 -270 Z" fill="${C.hoodie}"/>`);
  s.push(`<path d="M-72 -176 Q0 -160 72 -176 L72 -166 Q0 -150 -72 -166 Z" fill="${C.hoodieDark}"/>`);
  // kangaroo pocket and drawstrings
  s.push(`<path d="M-36 -214 L36 -214 L46 -180 L-46 -180 Z" fill="${C.hoodieLight}" opacity=".7"/>`);
  s.push(`<path d="M-10 -280 L-13 -238 M10 -280 L13 -238" stroke="#fff" stroke-width="3" stroke-linecap="round"/>`);
  s.push(`<circle cx="-13" cy="-236" r="3" fill="#fff"/><circle cx="13" cy="-236" r="3" fill="#fff"/>`);
  // neck
  s.push(`<path d="M-13 -300 L13 -300 L15 -280 Q0 -274 -15 -280 Z" fill="${C.skinShade}"/>`);

  // head
  s.push(head(o));

  // arms (drawn after the torso)
  s.push(arms(o));
  s.push(`</g>`);
  return s.join('');
}

function head(o) {
  const s = [];
  const cy = -345;
  s.push(`<ellipse cx="-46" cy="${cy + 4}" rx="9" ry="13" fill="${C.skinShade}"/><ellipse cx="46" cy="${cy + 4}" rx="9" ry="13" fill="${C.skinShade}"/>`);
  s.push(`<ellipse cx="0" cy="${cy}" rx="45" ry="51" fill="${C.skin}"/>`);
  // hair with a swept quiff
  s.push(`<path d="M-47 ${cy + 2} C-56 ${cy - 52}, -20 ${cy - 74}, 12 ${cy - 70} C40 ${cy - 68}, 58 ${cy - 44}, 47 ${cy - 4} C44 ${cy - 26}, 38 ${cy - 34}, 26 ${cy - 38} C6 ${cy - 30}, -18 ${cy - 36}, -34 ${cy - 30} C-40 ${cy - 20}, -44 ${cy - 10}, -47 ${cy + 2} Z" fill="${C.hair}"/>`);
  s.push(`<path d="M-6 ${cy - 68} C14 ${cy - 86}, 44 ${cy - 76}, 46 ${cy - 54} C34 ${cy - 66}, 16 ${cy - 68}, -6 ${cy - 68} Z" fill="${C.hair}"/>`);
  // eyebrows
  const browTilt = o.mood === 'worried' || o.mood === 'think' ? 5 : 0;
  s.push(`<path d="M-28 ${cy - 20 + browTilt} L-9 ${cy - 23 - browTilt}" stroke="${C.hair}" stroke-width="4.5" stroke-linecap="round"/>`);
  s.push(`<path d="M9 ${cy - 23 - (o.mood === 'think' ? 4 : browTilt)} L28 ${cy - 20 + (o.mood === 'think' ? -2 : browTilt)}" stroke="${C.hair}" stroke-width="4.5" stroke-linecap="round"/>`);
  // eyes
  const ey = cy - 4;
  if (o.mood === 'happy') {
    s.push(`<path d="M-24 ${ey + 2} Q-18 ${ey - 5} -12 ${ey + 2} M12 ${ey + 2} Q18 ${ey - 5} 24 ${ey + 2}" stroke="${C.ink}" stroke-width="3.5" fill="none" stroke-linecap="round"/>`);
  } else if (o.blink) {
    s.push(`<path d="M-24 ${ey} L-12 ${ey} M12 ${ey} L24 ${ey}" stroke="${C.ink}" stroke-width="3" stroke-linecap="round"/>`);
  } else {
    const lx = o.mood === 'think' ? 3 : 0, ly = o.look === 'down' ? 3 : (o.mood === 'think' ? -3 : 0);
    s.push(`<circle cx="${-18 + lx}" cy="${ey + ly}" r="4.5" fill="${C.ink}"/><circle cx="${18 + lx}" cy="${ey + ly}" r="4.5" fill="${C.ink}"/>`);
    s.push(`<circle cx="${-16.5 + lx}" cy="${ey + ly - 1.5}" r="1.4" fill="#fff"/><circle cx="${19.5 + lx}" cy="${ey + ly - 1.5}" r="1.4" fill="#fff"/>`);
  }
  // round glasses
  s.push(`<circle cx="-18" cy="${ey}" r="14" fill="#fff" fill-opacity=".18" stroke="${C.ink}" stroke-width="3"/>`);
  s.push(`<circle cx="18" cy="${ey}" r="14" fill="#fff" fill-opacity=".18" stroke="${C.ink}" stroke-width="3"/>`);
  s.push(`<path d="M-4 ${ey - 1} Q0 ${ey - 4} 4 ${ey - 1} M-32 ${ey - 2} L-44 ${ey - 5} M32 ${ey - 2} L44 ${ey - 5}" stroke="${C.ink}" stroke-width="3" fill="none"/>`);
  // nose and cheeks
  s.push(`<path d="M1 ${cy + 6} Q6 ${cy + 16} 0 ${cy + 18}" stroke="${C.skinShade}" stroke-width="3.5" fill="none" stroke-linecap="round"/>`);
  if (o.mood === 'happy') s.push(`<circle cx="-28" cy="${cy + 18}" r="7" fill="#f2a08a" opacity=".55"/><circle cx="28" cy="${cy + 18}" r="7" fill="#f2a08a" opacity=".55"/>`);
  // mouth
  const my = cy + 30;
  if (o.mood === 'happy') s.push(`<path d="M-15 ${my - 3} Q0 ${my + 14} 15 ${my - 3} Z" fill="#8a3324"/><path d="M-10 ${my + 1} Q0 ${my + 6} 10 ${my + 1}" stroke="#fff" stroke-width="3" fill="none"/>`);
  else if (o.mood === 'worried') s.push(`<path d="M-11 ${my + 3} Q0 ${my - 5} 11 ${my + 3}" stroke="#8a3324" stroke-width="4" fill="none" stroke-linecap="round"/>`);
  else if (o.mood === 'think') s.push(`<path d="M-6 ${my} L10 ${my - 2}" stroke="#8a3324" stroke-width="4" fill="none" stroke-linecap="round"/>`);
  else s.push(`<path d="M-11 ${my} Q0 ${my + 5} 11 ${my}" stroke="#8a3324" stroke-width="4" fill="none" stroke-linecap="round"/>`);
  return s.join('');
}

function sleeve(d, hx, hy) {
  return `<path d="${d}" stroke="${C.hoodie}" stroke-width="27" fill="none" stroke-linecap="round" stroke-linejoin="round"/>` +
    `<circle cx="${hx}" cy="${hy}" r="13" fill="${C.skin}"/>`;
}

function phone(x, y, flash) {
  return `<g transform="translate(${x} ${y}) rotate(-4)">` +
    `<rect x="-19" y="-34" width="38" height="68" rx="8" fill="#1d1f24"/>` +
    `<rect x="-14" y="-28" width="12" height="12" rx="4" fill="#3a3d45"/><circle cx="-8" cy="-22" r="3" fill="#111"/>` +
    (flash ? `<rect x="-24" y="-39" width="48" height="78" rx="11" fill="none" stroke="#fff" stroke-width="5" opacity=".9"/>` : '') +
    `</g>`;
}

function arms(o) {
  const s = [];
  if (o.arms === 'phone') {
    // both hands hold the phone in front of the chest
    s.push(sleeve('M-60 -262 Q-84 -200 -24 -222', -20, -224));
    s.push(sleeve('M60 -262 Q84 -200 24 -222', 20, -224));
    s.push(phone(0, -236, o.flash));
    s.push(`<circle cx="-20" cy="-218" r="11" fill="${C.skin}"/><circle cx="20" cy="-218" r="11" fill="${C.skin}"/>`);
  } else if (o.arms === 'relax') {
    // hands behind the head
    s.push(sleeve('M-60 -262 Q-100 -300 -52 -370', -50, -372));
    s.push(sleeve('M60 -262 Q100 -300 52 -370', 50, -372));
  } else if (o.arms === 'thumb') {
    s.push(sleeve('M-60 -262 Q-78 -210 -72 -170', -72, -168));
    s.push(sleeve('M60 -262 Q104 -290 96 -346', 96, -350));
    s.push(`<rect x="90" y="-384" width="12" height="28" rx="6" fill="${C.skin}"/>`);
  } else if (o.arms === 'chin') {
    s.push(sleeve('M-60 -262 Q-82 -215 -30 -200', -28, -200));
    s.push(sleeve('M60 -262 Q86 -230 26 -300', 22, -302));
  } else {
    s.push(sleeve('M-60 -262 Q-78 -210 -72 -170', -72, -168));
    s.push(sleeve('M60 -262 Q78 -210 72 -170', 72, -168));
  }
  return s.join('');
}
