import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

// This runs in Node.js - Don't use client-side code here (browser APIs, JSX...)

/**
 * Creating a sidebar enables you to:
 - create an ordered group of docs
 - render a sidebar for each doc of that group
 - provide next/previous navigation

 The sidebars can be generated from the filesystem, or explicitly defined here.

 Create as many sidebars as you want.
 */
const sidebars: SidebarsConfig = {
  // By default, Docusaurus generates a sidebar from the docs folder structure
  tutorialSidebar: [
    'intro',
    {
      type: 'category',
      label: 'Getting Started',
      items: [
        'getting-started/overview',
        'getting-started/hardware',
        'getting-started/prerequisites',
      ],
    },
    {
      type: 'category',
      label: 'Kubernetes Setup',
      items: [
        'kubernetes/installation',
      ],
    },
    {
      type: 'category',
      label: 'Monitoring',
      items: [
        'monitoring/overview',
      ],
    },
    {
      type: 'doc',
      id: 'todo',
    },
  ],
};

export default sidebars;
