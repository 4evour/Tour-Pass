const fs = require('fs');
let c = fs.readFileSync('web/editor/src/components/PoiCard.tsx', 'utf-8');

// Update sidebar variant: better no-image placeholder
const oldSidebar = `{poi.image_url ? (
          <img src={\`/\${poi.image_url}\`} alt={poi.name} className="w-10 h-10 rounded object-cover flex-shrink-0" loading="lazy" onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }} />
        ) : (
          <span className="text-lg">{TYPE_ICONS[poi.type] || '📍'}</span>
        )}`;

const newSidebar = `{poi.image_url ? (
          <img src={\`/\${poi.image_url}\`} alt={poi.name} className="w-10 h-10 rounded object-cover flex-shrink-0" loading="lazy" onError={(e) => { (e.target as HTMLImageElement).src = ''; (e.target as HTMLImageElement).style.display = 'none'; }} />
        ) : (
          <div className="w-10 h-10 rounded bg-gray-100 flex items-center justify-center flex-shrink-0 text-xs text-gray-400">
            {TYPE_ICONS[poi.type] || '📍'}
          </div>
        )}`;

if (c.includes(oldSidebar)) {
  c = c.replace(oldSidebar, newSidebar);
  console.log('Updated sidebar fallback');
} else {
  console.log('Sidebar pattern not found, checking...');
  if (c.includes('poi.image_url')) console.log('  image_url check exists');
}

// Update timeline variant too
const oldTimeline = `{poi.image_url ? (
        <img src={\`/\${poi.image_url}\`} alt={poi.name} className="w-10 h-10 rounded object-cover flex-shrink-0" loading="lazy" onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }} />
      ) : (
        <span className="text-lg flex-shrink-0">{TYPE_ICONS[poi.type] || '📍'}</span>
      )}`;

const newTimeline = `{poi.image_url ? (
        <img src={\`/\${poi.image_url}\`} alt={poi.name} className="w-10 h-10 rounded object-cover flex-shrink-0" loading="lazy" onError={(e) => { (e.target as HTMLImageElement).src = ''; (e.target as HTMLImageElement).style.display = 'none'; }} />
      ) : (
        <div className="w-10 h-10 rounded bg-gray-100 flex items-center justify-center flex-shrink-0 text-xs text-gray-400">
          {TYPE_ICONS[poi.type] || '📍'}
        </div>
      )}`;

if (c.includes(oldTimeline)) {
  c = c.replace(oldTimeline, newTimeline);
  console.log('Updated timeline fallback');
} else {
  console.log('Timeline pattern not found');
}

fs.writeFileSync('web/editor/src/components/PoiCard.tsx', c);
console.log('Done');
