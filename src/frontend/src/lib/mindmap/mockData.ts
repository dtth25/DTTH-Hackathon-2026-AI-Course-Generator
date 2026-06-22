import { MindMapData } from './types';

export const mockMindMapData: MindMapData = {
  root: {
    id: 'root',
    label: 'Machine Learning Fundamentals',
    citations: [
      { page: 1, source: 'ml_textbook.pdf', chunk_id: 'chunk_001' },
    ],
  },
  branches: [
    {
      id: 'branch_1',
      label: 'Supervised Learning',
      citations: [{ page: 5, source: 'ml_textbook.pdf', chunk_id: 'chunk_005' }],
      children: [
        {
          id: 'branch_1_1',
          label: 'Classification',
          citations: [
            { page: 8, source: 'ml_textbook.pdf', chunk_id: 'chunk_008' },
          ],
          children: [
            {
              id: 'leaf_1_1_1',
              label: 'Logistic Regression',
              citations: [
                {
                  page: 10,
                  source: 'ml_textbook.pdf',
                  chunk_id: 'chunk_010',
                },
              ],
            },
            {
              id: 'leaf_1_1_2',
              label: 'Decision Trees',
              citations: [
                { page: 14, source: 'ml_textbook.pdf', chunk_id: 'chunk_014' },
              ],
            },
          ],
        },
        {
          id: 'branch_1_2',
          label: 'Regression',
          citations: [{ page: 20, source: 'ml_textbook.pdf', chunk_id: 'chunk_020' }],
          children: [
            {
              id: 'leaf_1_2_1',
              label: 'Linear Regression',
              citations: [
                { page: 22, source: 'ml_textbook.pdf', chunk_id: 'chunk_022' },
              ],
            },
            {
              id: 'leaf_1_2_2',
              label: 'Polynomial Regression',
              citations: [
                { page: 26, source: 'ml_textbook.pdf', chunk_id: 'chunk_026' },
              ],
            },
          ],
        },
      ],
    },
    {
      id: 'branch_2',
      label: 'Unsupervised Learning',
      citations: [{ page: 35, source: 'ml_textbook.pdf', chunk_id: 'chunk_035' }],
      children: [
        {
          id: 'branch_2_1',
          label: 'Clustering',
          citations: [
            { page: 38, source: 'ml_textbook.pdf', chunk_id: 'chunk_038' },
          ],
        },
        {
          id: 'branch_2_2',
          label: 'Dimensionality Reduction',
          citations: [
            { page: 45, source: 'ml_textbook.pdf', chunk_id: 'chunk_045' },
          ],
        },
      ],
    },
    {
      id: 'branch_3',
      label: 'Neural Networks',
      citations: [{ page: 50, source: 'ml_textbook.pdf', chunk_id: 'chunk_050' }],
      children: [
        {
          id: 'branch_3_1',
          label: 'Deep Learning',
          citations: [
            { page: 55, source: 'ml_textbook.pdf', chunk_id: 'chunk_055' },
          ],
        },
        {
          id: 'branch_3_2',
          label: 'CNN',
          citations: [{ page: 62, source: 'ml_textbook.pdf', chunk_id: 'chunk_062' }],
        },
      ],
    },
  ],
};