"use client";

import { Linkedin, Twitter } from "lucide-react";
import Image from "next/image";
import Link from "next/link";

export function Footer() {
	return (
		<footer className="border-t border-slate-200 py-16 px-4 sm:px-6 lg:px-8 bg-gradient-to-b from-white to-slate-50">
			<div className="max-w-6xl mx-auto">
				<div className="grid grid-cols-2 md:grid-cols-4 gap-8 mb-12">
					{/* Logo Column */}
					<div className="col-span-2 md:col-span-1">
						<div className="flex items-center gap-2 mb-4">
							<div className="h-9 w-9 rounded-xl bg-white flex items-center justify-center shadow-lg shadow-indigo-500/25 p-1">
								<Image
									src="/reflexio_fav.svg"
									alt="Reflexio"
									width={28}
									height={28}
								/>
							</div>
							<span className="font-bold text-xl text-slate-800">Reflexio</span>
						</div>
						<p className="text-sm text-slate-600 leading-relaxed mb-4">
							The learning layer that turns AI agents into self-improving
							systems.
						</p>
						{/* Social Links */}
						<div className="flex gap-3">
							<Link
								href="#"
								className="w-9 h-9 rounded-lg bg-slate-100 hover:bg-slate-200 flex items-center justify-center text-slate-600 hover:text-slate-800 transition-colors"
							>
								<Twitter className="h-4 w-4" />
							</Link>
							<Link
								href="#"
								className="w-9 h-9 rounded-lg bg-slate-100 hover:bg-slate-200 flex items-center justify-center text-slate-600 hover:text-slate-800 transition-colors"
							>
								<Linkedin className="h-4 w-4" />
							</Link>
						</div>
					</div>

					{/* Product Links */}
					<div>
						<h4 className="font-semibold text-slate-800 mb-4 text-sm">
							Product
						</h4>
						<ul className="space-y-3">
							<li>
								<a
									href="#features"
									className="text-sm text-slate-600 hover:text-indigo-600 transition-colors"
								>
									Features
								</a>
							</li>
							<li>
								<a
									href="#how-it-works"
									className="text-sm text-slate-600 hover:text-indigo-600 transition-colors"
								>
									How It Works
								</a>
							</li>
							<li>
								<a
									href="/docs/"
									target="_blank"
									rel="noopener noreferrer"
									className="text-sm text-slate-600 hover:text-indigo-600 transition-colors"
								>
									Documentation
								</a>
							</li>
							<li>
								<a
									href="/docs/api-reference/"
									target="_blank"
									rel="noopener noreferrer"
									className="text-sm text-slate-600 hover:text-indigo-600 transition-colors"
								>
									API Reference
								</a>
							</li>
						</ul>
					</div>

					{/* Resources Links */}
					<div>
						<h4 className="font-semibold text-slate-800 mb-4 text-sm">
							Resources
						</h4>
						<ul className="space-y-3">
							<li>
								<Link
									href="#"
									className="text-sm text-slate-600 hover:text-indigo-600 transition-colors"
								>
									Blog
								</Link>
							</li>
							<li>
								<Link
									href="#"
									className="text-sm text-slate-600 hover:text-indigo-600 transition-colors"
								>
									Community
								</Link>
							</li>
							<li>
								<Link
									href="#"
									className="text-sm text-slate-600 hover:text-indigo-600 transition-colors"
								>
									Support
								</Link>
							</li>
						</ul>
					</div>

					{/* Legal Links */}
					<div>
						<h4 className="font-semibold text-slate-800 mb-4 text-sm">Legal</h4>
						<ul className="space-y-3">
							<li>
								<Link
									href="#"
									className="text-sm text-slate-600 hover:text-indigo-600 transition-colors"
								>
									Privacy Policy
								</Link>
							</li>
							<li>
								<Link
									href="#"
									className="text-sm text-slate-600 hover:text-indigo-600 transition-colors"
								>
									Terms of Service
								</Link>
							</li>
							<li>
								<Link
									href="#"
									className="text-sm text-slate-600 hover:text-indigo-600 transition-colors"
								>
									Cookie Policy
								</Link>
							</li>
						</ul>
					</div>
				</div>

				{/* Bottom bar */}
				<div className="pt-8 border-t border-slate-200">
					<div className="flex flex-col sm:flex-row justify-between items-center gap-4">
						<p className="text-sm text-slate-500">
							&copy; {new Date().getFullYear()} Reflexio. All rights reserved.
						</p>
						<p className="text-sm text-slate-500">
							Built with care for developers
						</p>
					</div>
				</div>
			</div>
		</footer>
	);
}
