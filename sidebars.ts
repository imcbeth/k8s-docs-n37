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
        'kubernetes/cluster-configuration',
      ],
    },
    {
      type: 'category',
      label: 'Networking',
      items: [
        'networking/overview',
        'networking/terraform',
      ],
    },
    {
      type: 'category',
      label: 'Storage',
      items: [
        'storage/synology-csi',
      ],
    },
    {
      type: 'category',
      label: 'Applications',
      items: [
        'applications/argocd',
        'applications/metallb',
        'applications/unipoller',
        'applications/kube-prometheus-stack',
        'applications/snmp-exporter',
        'applications/loki',
        'applications/cert-manager',
        'applications/external-dns',
        'applications/metrics-server',
        'applications/velero',
        'applications/blackbox-exporter',
        'applications/ingress-nginx',
        {
          type: 'category',
          label: 'Trivy Operator',
          items: [
            'applications/trivy-operator',
            'applications/trivy-vulnerability-remediation',
          ],
        },
      ],
    },
    {
      type: 'category',
      label: 'Monitoring',
      items: [
        'monitoring/overview',
        'monitoring/grafana-dashboards',
      ],
    },
    {
      type: 'category',
      label: 'Security',
      items: [
        'security/secrets-management',
        'security/network-policies',
      ],
    },
    {
      type: 'category',
      label: 'Troubleshooting',
      items: [
        'troubleshooting/monitoring',
        'troubleshooting/common-issues',
      ],
    },
    {
      type: 'doc',
      id: 'todo',
    },
  ],
};

export default sidebars;
