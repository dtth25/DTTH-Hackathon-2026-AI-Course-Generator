# Mind Map Prototype Setup Instructions

## Prerequisites

- Node.js 18+ installed
- npm or yarn package manager

## Installation Steps

### 1. Install Dependencies

```bash
# From the frontend directory
cd src/frontend

# Install React Flow and its types
npm install reactflow
npm install -D @types/reactflow

# Or using yarn
yarn add reactflow
yarn add -D @types/reactflow

# Or using pnpm
pnpm add reactflow
pnpm add -D @types/reactflow
```

### 2. Run Development Server

```bash
npm run dev
```

### 3. Access Prototype

Open browser and navigate to:
```
http://localhost:3000/mindmap/prototype
```

## Project Structure

```
src/frontend/src/
├── app/
│   └── mindmap/
│       └── prototype/
│           ├── page.tsx          # Prototype page
│           └── SETUP.md          # This file
├── components/
│   └── mindmap/
│       ├── MindMapViewer.tsx     # Main viewer component
│       ├── CitationPanel.tsx     # Citation display panel
│       └── nodes/
│           ├── RootNode.tsx      # Root node (center)
│           └── BranchNode.tsx    # Branch nodes (children)
└── lib/
    └── mindmap/
        ├── types.ts              # TypeScript interfaces
        ├── mockData.ts           # Mock data for testing
        └── convertToFlow.ts      # Convert MindMap to React Flow format
```

## Features Implemented

### 1. **Radial Tree Layout**
- Root node centered
- Branches spread radially outward
- Auto-positioning based on depth

### 2. **Custom Nodes**
- **RootNode**: Blue gradient, larger, shows book icon
- **BranchNode**: Color-coded by depth (emerald, amber, purple, pink)
- Both show citation badges (page numbers)

### 3. **Interactive Features**
- **Pan**: Click and drag canvas
- **Zoom**: Mouse wheel or +/- controls
- **Click Node**: Shows citation panel on right
- **Expand/Collapse**: Toggle button on nodes with children
- **Minimap**: Navigate large mind maps

### 4. **Citation Panel**
- Shows all citations for selected node
- Displays: page number, source file, chunk_id
- Clean, readable design

### 5. **Responsive Design**
- Works on laptop screens (1280px+)
- Flexible container sizing
- Tailwind CSS styling

## Mock Data

The prototype uses sample data from `mockData.ts`:
- **Topic**: Machine Learning Fundamentals
- **Structure**: Root → 3 branches → multiple sub-branches
- **Citations**: Each node has page references from `ml_textbook.pdf`

## Integration with Backend

When backend is ready, replace mock data with API call:

```typescript
// Replace this in page.tsx:
import { mockMindMapData } from '@/lib/mindmap/mockData';
<MindMapViewer data={mockMindMapData} />

// With this:
const [data, setData] = useState<MindMapData | null>(null);
useEffect(() => {
  fetch('/api/generate-mindmap', {
    method: 'POST',
    body: JSON.stringify({ file_id: 'your-file-id' }),
  })
    .then(res => res.json())
    .then(response => setData(response.mindmap));
}, []);
```

## API Contract (Expected)

```typescript
interface GenerateMindMapResponse {
  mindmap: {
    root: {
      id: string;
      label: string;
      citations: Array<{
        page: number;
        source: string;
        chunk_id: string;
      }>;
    };
    branches: Array<{
      id: string;
      label: string;
      citations: Array<{...}>;
      children?: Array<{...}>;
    }>;
  };
}
```

## Troubleshooting

### TypeScript Errors
If you see "Cannot find module 'reactflow'":
```bash
npm install reactflow @types/reactflow
```

### Styles Not Loading
Make sure `reactflow/dist/style.css` is imported in MindMapViewer.tsx

### Nodes Not Rendering
Check browser console for errors. Ensure nodeTypes are registered correctly.

## Next Steps

1. Install dependencies
2. Run `npm run dev`
3. Open http://localhost:3000/mindmap/prototype
4. Test interactive features
5. Replace mock data with real API when backend is ready