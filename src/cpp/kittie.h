#ifndef __KITTIE_H__
#	define __KITTIE_H__


#	include <stdlib.h>
#	include <string>
#	include <vector>
#	include <algorithm>
#	include <iostream>
#	include <fstream>
#	include <cstdio>
#	include <adios2.h>

#	include "yaml-cpp/yaml.h"


#	ifdef USE_MPI
#		include <mpi.h>
#	else
		class MPI_Comm {};
		int MPI_Comm_dup(MPI_Comm incomm, MPI_Comm* outcomm);
		int MPI_Comm_rank(MPI_Comm incomm, int* rank);
		int MPI_Barrier(MPI_Comm incomm);
#	endif


	namespace kittie 
	{

		class Coupler
		{
			public:
				std::string groupname;
				std::string filename;
				std::string cwriting;
				std::string creading;
				std::vector<std::string> allcreading;
				adios2::IO* io;
				adios2::Engine engine;
				adios2::Mode mode;
				MPI_Comm comm;
				int rank;
				bool init;
				bool LockFile;


				// Constructors
				Coupler(const std::string ingroupname);


				// Destructor
				~Coupler();


				// Methods
				adios2::StepStatus begin_step(const int step, const double timeout=0.0);
				adios2::StepStatus begin_step(const double timeout=0.0);
				void end_step();
				void close();
				void _open(MPI_Comm incomm, const std::string infilename, const adios2::Mode inmode);


			protected:
				void Until_Nonexistent_Write();
				void Until_Nonexistent_Read(int verify_level=3);
				void AcquireLock();
				void ReleaseLock();
				void _CoupleOpen();
				void _lockfile();
				void begin_write();
				adios2::StepStatus FileSeek(bool &found, const int step, const double timeout=-1.0);
		};


		// "Private"
		bool mpi;
		MPI_Comm comm;
		adios2::ADIOS* adios;
		extern std::map<std::string, Coupler*> Couplers;
		std::vector<std::string> _FileMethods {"bpfile", "bp", "bp3", "hdf5"};
		std::string writing = ".writing";
		std::string reading = ".reading";
		std::vector<std::string> allreading;
		std::string myreading;

		std::string appname;
		int ngroups;
		std::vector<std::string> groupnames;

		int nnames;
		std::map<std::string, std::string> setengines;
		std::map<std::string, std::map<std::string, std::string>> setparams;

		void _buildyaml();
		void _groupsyaml();
		void _codesyaml();
		void _yaml_setup();

		bool Exists(std::string filename);
		void Touch(std::string filename);
		adios2::Engine _mopen(const std::string groupname, const std::string filename, const adios2::Mode mode, MPI_Comm comm);


		// "Public"
		adios2::IO declare_io(const std::string groupname);
		void finalize();
		adios2::Engine open(const std::string groupname, const std::string filename, const adios2::Mode mode);

#	ifdef USE_MPI
			adios2::Engine open(const std::string groupname, const std::string filename, const adios2::Mode mode, MPI_Comm comm);
			void initialize(const std::string &filename="", MPI_Comm comm=MPI_COMM_SELF, const bool DebugMode=true);
			void initialize(MPI_Comm comm, const bool DebugMode=true);
#	else
			void initialize(const std::string &filename="", const bool DebugMode=true);
			void initialize(const bool DebugMode=true);
#	endif
		
	}

#endif
